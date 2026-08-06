import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { joinByEntranceCode } from '@/api/auth'
import { saveCustomerSession, clearCustomerSession } from '@/utils/auth'
import { isDiningIdentityError } from '@/utils/dining'

vi.mock('@/api/order', () => ({
  createOrder: vi.fn(),
  createWxPayOrder: vi.fn(),
  getOrderStatus: vi.fn(),
}))
vi.mock('@/api/auth', () => ({
  joinByEntranceCode: vi.fn(),
}))
vi.mock('@/utils/auth', () => ({
  saveCustomerSession: vi.fn(),
  clearCustomerSession: vi.fn(),
}))
vi.mock('@/utils/dining', () => ({
  isDiningIdentityError: vi.fn(() => false),
}))

// 一份齐全的、贴近 menu.vue 真实传参的默认状态，覆盖购物车里有一件商品、
// 桌台会话正常、可以下单。每条用例按需覆盖其中某几个字段。
function setup(overrides = {}) {
  const cartItem = { id: 'dish_1', name: '招牌炒饭', price: 20, qty: 1, orderName: '招牌炒饭' }
  const state = {
    shopId: ref('shop_1'),
    tableNo: ref('A01'),
    diningSessionId: ref('sess_1'),
    diningParticipantToken: ref('tok_1'),
    diningClientId: ref('client_1'),
    orderNo: ref(''),
    orderId: ref(''),
    orderStatus: ref('pending'),
    successItems: ref([]),
    successTotal: ref(0),
    successDiscount: ref(0),
    showCheckoutAuth: ref(false),
    authorizing: ref(false),
    authActionStatus: ref('idle'),
    pendingPaymentIntent: ref(null),
    paying: ref(false),
    paymentFailed: ref(false),
    payAmount: ref(0),
    pendingOrderId: ref(''),
    pendingSubmitRequestId: ref(''),
    myOrders: ref([]),
    showOrders: ref(false),
    showCart: ref(true),
    showSuccess: ref(false),
    ordering: ref(false),
    tableSessionClosed: ref(false),
    paymentMode: ref('prepay'),
    reminderRequested: ref(false),
    earnedCoupon: ref(null),
    cart: ref({ dish_1: 1 }),
    specCartItems: ref([]),
    remark: ref(''),
    selectedCouponId: ref(null),
    totalPrice: ref(20),
    cartItems: ref([cartItem]),
    finalPrice: ref(20),
    wechatPayAmount: ref(20),
    isPrepayMode: ref(true),
    canSubmitOrder: ref(true),
  }
  const callbacks = {
    wxLogin: vi.fn(() => Promise.resolve('wx_code')),
    ensureDiningSession: vi.fn(() => Promise.resolve(true)),
    bindCurrentDiningParticipant: vi.fn(() => Promise.resolve()),
    syncDiningOrders: vi.fn(() => Promise.resolve(true)),
    normalizePaymentMode: vi.fn((mode) => mode || 'prepay'),
    refreshCustomerAuthState: vi.fn(),
    saveMyOrders: vi.fn(),
    startStatusPoll: vi.fn(),
    consumeWelcomeCoupon: vi.fn(() => null),
  }
  const merged = { ...state, ...callbacks, ...overrides }
  const checkout = useCheckout(merged)
  return { state, callbacks, checkout }
}

describe('useCheckout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  describe('goCheckout', () => {
    it('正在下单/支付/授权中时点击去结算是无效操作', () => {
      const { state, checkout } = setup()
      state.paying.value = true

      checkout.goCheckout()

      expect(createOrder).not.toHaveBeenCalled()
    })

    it('不能下单时弹提示，不发请求', () => {
      const { state, checkout } = setup()
      state.canSubmitOrder.value = false
      state.tableSessionClosed.value = true

      checkout.goCheckout()

      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('已结束') })
      )
      expect(createOrder).not.toHaveBeenCalled()
    })

    it('已经有待支付订单时直接走支付，不重新下单', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: {} })
      createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'pending' } })

      checkout.goCheckout()
      await vi.waitFor(() => expect(createWxPayOrder).toHaveBeenCalled())

      expect(createOrder).not.toHaveBeenCalled()
    })
  })

  describe('performSubmitOrder - 提交成功', () => {
    it('免单（need_payment:false）时直接标记成功，不再走微信支付', async () => {
      const { state, checkout, callbacks } = setup()
      createOrder.mockResolvedValue({
        data: { id: 'order_1', order_no: 'ON20260806001', pay_amount: 0, need_payment: false, status: 'done' },
      })

      const ok = await checkout.performSubmitOrder()

      expect(ok).toBe(true)
      expect(createWxPayOrder).not.toHaveBeenCalled()
      expect(state.showSuccess.value).toBe(true)
      expect(state.orderId.value).toBe('order_1')
      expect(state.cart.value).toEqual({})
      expect(callbacks.startStatusPoll).toHaveBeenCalledWith('order_1')
      expect(callbacks.saveMyOrders).toHaveBeenCalled()
    })

    it('需要支付时创建订单后自动走去支付，微信 requestPayment 成功即完成', async () => {
      const { state, checkout } = setup()
      createOrder.mockResolvedValue({
        data: { id: 'order_1', order_no: 'ON20260806001', pay_amount: 20, need_payment: true },
      })
      getOrderStatus.mockResolvedValue({ data: {} }) // recoverPendingPaymentResult: 尚未支付，放行
      createWxPayOrder.mockResolvedValue({
        data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
      })

      const ok = await checkout.performSubmitOrder()

      expect(ok).toBe(true)
      expect(uni.requestPayment).toHaveBeenCalledWith(
        expect.objectContaining({ provider: 'wxpay', timeStamp: '1' })
      )
      expect(state.showSuccess.value).toBe(true)
    })

    it('提交请求体带上桌号/购物车/优惠券/幂等请求号', async () => {
      const { state, checkout } = setup()
      state.selectedCouponId.value = 'coupon_9'
      state.remark.value = ' 不要辣 '
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      await checkout.performSubmitOrder()

      expect(createOrder).toHaveBeenCalledWith(
        expect.objectContaining({
          table: 'A01',
          shop: 'shop_1',
          total: 20,
          remark: '不要辣',
          coupon_id: 'coupon_9',
          dining_session_id: 'sess_1',
          participant_token: 'tok_1',
          request_id: expect.any(String),
          items: [expect.objectContaining({ dish_id: 'dish_1', qty: 1 })],
        }),
        { authRedirect: false }
      )
    })

    it('弱网超时等临时失败后重新提交，请求号保持不变，后端能靠它去重', async () => {
      // pendingSubmitRequestId 只在真正下单成功（_handlePaySuccess）时才会被清空
      // 重置，为的就是同一次结算内"提交失败/超时后用户再点一次"这种场景，
      // 后端拿相同的 request_id 能识别成同一次提交、不会建出第二张订单。
      const { checkout } = setup()
      createOrder.mockRejectedValueOnce(new Error('request:fail timeout'))

      await checkout.performSubmitOrder()
      const firstRequestId = createOrder.mock.calls[0][0].request_id
      expect(firstRequestId).toBeTruthy()

      createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false } })
      await checkout.performSubmitOrder()
      const secondRequestId = createOrder.mock.calls[1][0].request_id

      expect(secondRequestId).toBe(firstRequestId)
    })
  })

  describe('performSubmitOrder - 本桌身份失效自动重试', () => {
    it('后端因身份失效报错时，静默重建身份后自动重试一次并成功', async () => {
      const { state, checkout, callbacks } = setup()
      const identityError = new Error('identity mismatch')
      isDiningIdentityError.mockImplementation((err) => err === identityError)
      createOrder
        .mockRejectedValueOnce(identityError)
        .mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false } })

      const ok = await checkout.performSubmitOrder()

      expect(ok).toBe(true)
      expect(createOrder).toHaveBeenCalledTimes(2)
      // 第一次是 sessionReady 检查那次调用，第二次是重试前 force 重建那次
      expect(callbacks.ensureDiningSession).toHaveBeenCalledWith(true)
      expect(state.tableSessionClosed.value).toBe(false)
    })

    it('身份失效后即使重建也失败时，不会无限重试，直接兜底提示失败', async () => {
      const { callbacks, checkout } = setup()
      const identityError = new Error('identity mismatch')
      isDiningIdentityError.mockImplementation((err) => err === identityError)
      createOrder.mockRejectedValue(identityError)
      callbacks.ensureDiningSession.mockImplementation((force) => Promise.resolve(!force ? true : false))

      const ok = await checkout.performSubmitOrder()

      expect(ok).toBe(false)
      // sessionReady 检查一次 + 重试前重建一次 = 2 次，重建失败后不会再递归
      expect(createOrder).toHaveBeenCalledTimes(1)
    })

    it('已经是重试状态时不再二次重建身份，避免死循环', async () => {
      const { callbacks, checkout } = setup()
      const identityError = new Error('identity mismatch')
      isDiningIdentityError.mockImplementation((err) => err === identityError)
      createOrder.mockRejectedValue(identityError)

      const ok = await checkout.performSubmitOrder(true)

      expect(ok).toBe(false)
      expect(callbacks.ensureDiningSession).not.toHaveBeenCalledWith(true)
    })
  })

  describe('performSubmitOrder - 结账授权失效（401/403）', () => {
    it('后端返回未登录/授权失效时清空会员会话并弹出授权面板，而不是通用报错', async () => {
      const { state, checkout, callbacks } = setup()
      const authError = new Error('NEED_LOGIN')
      authError.statusCode = 401
      createOrder.mockRejectedValue(authError)

      const ok = await checkout.performSubmitOrder()

      expect(ok).toBe(false)
      expect(clearCustomerSession).toHaveBeenCalledTimes(1)
      expect(callbacks.refreshCustomerAuthState).toHaveBeenCalledTimes(1)
      expect(state.showCheckoutAuth.value).toBe(true)
      expect(uni.showToast).not.toHaveBeenCalled()
    })
  })

  describe('performSubmitOrder - 本桌会话不可用', () => {
    it('ensureDiningSession 返回 false 时提示重新扫码，不发下单请求', async () => {
      const { checkout } = setup({ ensureDiningSession: vi.fn(() => Promise.resolve(false)) })

      const ok = await checkout.performSubmitOrder()

      expect(ok).toBe(false)
      expect(createOrder).not.toHaveBeenCalled()
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('重新扫码') })
      )
    })
  })

  describe('submitOrder - 防重复提交锁', () => {
    it('已经在提交中时再次调用直接返回 false，不发第二次请求', async () => {
      const { state, checkout } = setup()
      state.ordering.value = true

      const ok = await checkout.submitOrder()

      expect(ok).toBe(false)
      expect(createOrder).not.toHaveBeenCalled()
    })

    it('提交完成后无论成功失败都会释放锁', async () => {
      const { state, checkout } = setup()
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      await checkout.submitOrder()

      expect(state.ordering.value).toBe(false)
    })
  })

  describe('confirmPay', () => {
    it('没有待支付订单时直接返回 false，不发请求', async () => {
      const { checkout } = setup()

      const ok = await checkout.confirmPay()

      expect(ok).toBe(false)
      expect(createWxPayOrder).not.toHaveBeenCalled()
    })

    it('正在支付中时重复调用直接返回 false', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      state.paying.value = true

      const ok = await checkout.confirmPay()

      expect(ok).toBe(false)
      expect(createWxPayOrder).not.toHaveBeenCalled()
    })

    it('发起支付前先核对订单是否已经支付过，已支付则直接对账并放弃重复扣款', async () => {
      // 这里对齐的是"核对"而不是"重新展示成功页"——真正的成功页只在刚完成
      // 一次支付动作时由 _handlePaySuccess 触发，recoverPendingPaymentResult
      // 是页面重进/断线重连时的对账兜底，职责不一样，不应该混着断言。
      const { state, checkout, callbacks } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: { status: 'done', payment_status: 'paid' } })

      const ok = await checkout.confirmPay()

      expect(ok).toBe(true)
      expect(createWxPayOrder).not.toHaveBeenCalled()
      expect(state.orderId.value).toBe('order_1')
      expect(state.orderStatus.value).toBe('done')
      expect(state.pendingOrderId.value).toBe('')
      expect(callbacks.startStatusPoll).toHaveBeenCalledWith('order_1')
    })

    it('微信支付成功后进入成功页并清空购物车', async () => {
      const { state, checkout, callbacks } = setup()
      state.pendingOrderId.value = 'order_1'
      state.payAmount.value = 20
      getOrderStatus.mockResolvedValue({ data: {} })
      createWxPayOrder.mockResolvedValue({
        data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
      })

      const ok = await checkout.confirmPay()

      expect(ok).toBe(true)
      expect(uni.requestPayment).toHaveBeenCalled()
      expect(state.showSuccess.value).toBe(true)
      expect(state.pendingOrderId.value).toBe('')
      expect(callbacks.saveMyOrders).toHaveBeenCalled()
    })

    it('用户在微信支付面板主动取消时，提示"已取消支付"而不是通用失败文案', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: {} })
      createWxPayOrder.mockResolvedValue({
        data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
      })
      uni.requestPayment.mockRejectedValueOnce({ errMsg: 'requestPayment:fail cancel' })

      const ok = await checkout.confirmPay()

      expect(ok).toBe(false)
      expect(state.paymentFailed.value).toBe(true)
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '已取消支付' })
      )
    })

    it('支付参数缺失等真实失败时标记 paymentFailed，界面能提示"重新支付"', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: {} })
      createWxPayOrder.mockResolvedValue({ data: {} }) // 没有 pay_params

      const ok = await checkout.confirmPay()

      expect(ok).toBe(false)
      expect(state.paymentFailed.value).toBe(true)
      expect(state.pendingOrderId.value).toBe('order_1') // 订单没丢，还能重新支付
    })

    it('支付环节遇到授权失效（401/403）时弹授权面板，不当成支付失败处理', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: {} })
      const authError = new Error('NEED_LOGIN')
      authError.statusCode = 401
      createWxPayOrder.mockRejectedValue(authError)

      const ok = await checkout.confirmPay()

      expect(ok).toBe(false)
      expect(state.showCheckoutAuth.value).toBe(true)
      expect(state.paymentFailed.value).toBe(false)
    })

    it('免费订单（satisfied by free flag）直接成功，不调起微信支付面板', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: {} })
      createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'done' } })

      const ok = await checkout.confirmPay()

      expect(ok).toBe(true)
      expect(uni.requestPayment).not.toHaveBeenCalled()
      expect(state.showSuccess.value).toBe(true)
    })
  })

  describe('recoverPendingPaymentResult', () => {
    it('本地和内存都没有待支付订单时直接返回 false', async () => {
      const { checkout } = setup()

      const ok = await checkout.recoverPendingPaymentResult()

      expect(ok).toBe(false)
      expect(getOrderStatus).not.toHaveBeenCalled()
    })

    it('订单已支付/已提交时，把本地状态跟服务端对齐并停止占用"待支付"标记', async () => {
      const { state, checkout, callbacks } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: { status: 'preparing' } })

      const ok = await checkout.recoverPendingPaymentResult()

      expect(ok).toBe(true)
      expect(state.orderId.value).toBe('order_1')
      expect(state.orderStatus.value).toBe('preparing')
      expect(state.pendingOrderId.value).toBe('')
      expect(callbacks.startStatusPoll).toHaveBeenCalledWith('order_1')
    })

    it('订单已取消/已拒单时清掉本地待支付标记，不当成"已支付"处理', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: { status: 'cancelled' } })

      const ok = await checkout.recoverPendingPaymentResult()

      expect(ok).toBe(false)
      expect(state.pendingOrderId.value).toBe('')
    })

    it('查询状态时网络异常，保留待支付标记以便下次再核对，不误清空', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockRejectedValue(new Error('network error'))

      const ok = await checkout.recoverPendingPaymentResult()

      expect(ok).toBe(false)
      expect(state.pendingOrderId.value).toBe('order_1')
    })

    it('并发调用时用重入锁避免同时触发两次核对', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      let resolveStatus
      getOrderStatus.mockReturnValue(new Promise((resolve) => { resolveStatus = resolve }))

      const first = checkout.recoverPendingPaymentResult()
      const second = checkout.recoverPendingPaymentResult()

      resolveStatus({ data: { status: 'preparing' } })
      const [firstResult, secondResult] = await Promise.all([first, second])

      expect(getOrderStatus).toHaveBeenCalledTimes(1)
      expect(firstResult).toBe(true)
      expect(secondResult).toBe(false)
    })
  })

  describe('requireCheckoutAuth', () => {
    it('弹出授权面板前会先清空可能已过期的会员会话', () => {
      const { state, checkout, callbacks } = setup()

      checkout.requireCheckoutAuth()

      expect(clearCustomerSession).toHaveBeenCalledTimes(1)
      expect(callbacks.refreshCustomerAuthState).toHaveBeenCalledTimes(1)
      expect(state.showCheckoutAuth.value).toBe(true)
      expect(state.authActionStatus.value).toBe('idle')
    })

    it('没有待处理的支付意图时会先把当前购物车快照存起来，授权完成后能继续下单', () => {
      const { state, checkout } = setup()

      checkout.requireCheckoutAuth()

      expect(state.pendingPaymentIntent.value).toEqual(
        expect.objectContaining({ merchantId: 'shop_1', tableId: 'A01' })
      )
    })
  })

  describe('handleCheckoutAuth', () => {
    it('没有拿到手机号授权码时提示未完成授权，不发任何请求', async () => {
      const { checkout } = setup()

      await checkout.handleCheckoutAuth({ detail: {} })

      expect(joinByEntranceCode).not.toHaveBeenCalled()
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('未完成授权') })
      )
    })

    it('授权成功后绑定拼桌身份、保存会员会话，并继续之前中断的下单/支付', async () => {
      const { state, checkout, callbacks } = setup()
      state.pendingPaymentIntent.value = { requestId: 'pay_1' }
      joinByEntranceCode.mockResolvedValue({ code: 200, data: { token: 'member_token' } })
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      await checkout.handleCheckoutAuth({ detail: { code: 'phone_code_1' } })

      expect(saveCustomerSession).toHaveBeenCalledWith({ token: 'member_token' })
      expect(callbacks.bindCurrentDiningParticipant).toHaveBeenCalledTimes(1)
      expect(state.showCheckoutAuth.value).toBe(false)
      expect(state.authorizing.value).toBe(false)
      expect(createOrder).toHaveBeenCalledTimes(1)
    })

    it('加入会员失败时回到 idle 状态并提示，不继续下单', async () => {
      const { state, checkout } = setup()
      joinByEntranceCode.mockResolvedValue({ code: 400, msg: '手机号已注册' })

      await checkout.handleCheckoutAuth({ detail: { code: 'phone_code_1' } })

      expect(state.authActionStatus.value).toBe('idle')
      expect(createOrder).not.toHaveBeenCalled()
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '手机号已注册' })
      )
    })
  })
})
