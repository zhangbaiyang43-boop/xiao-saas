import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { joinByEntranceCode } from '@/api/auth'
import { saveCustomerSession } from '@/utils/auth'
import { isDiningIdentityError } from '@/utils/dining'
import { savePendingSubmitIntent, restorePendingSubmitIntent } from '@/utils/pendingSubmitIntent'

// P0-A Pre-Submit Member Conversion: 普通 guest 点结算，先看到"加入会员并继续 /
// 直接支付"的选择层，选完才真正调用 createOrder——本文件只覆盖这条新增的
// goCheckout 分流 + joinMemberAndCheckout/checkoutAsGuest 状态机，不重复
// useCheckout.test.js 里已经覆盖的 performSubmitOrder/confirmPay 内部细节。

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
    orderSuccessTemplateId: ref('tmpl-order-success'),
    pickupReminderTemplateId: ref('tmpl-pickup'),
    showMemberCheckoutChoice: ref(false),
    memberChoiceJoining: ref(false),
    memberCheckoutBenefitsNeedRefresh: ref(false),
    isCustomerLoggedIn: ref(false),
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
    refreshAvailableCoupons: vi.fn(() => Promise.resolve()),
  }
  const merged = { ...state, ...callbacks, ...overrides }
  const checkout = useCheckout(merged)
  return { state, callbacks, checkout }
}

describe('P0-A member checkout choice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  describe('CASE 1: guest 点结算', () => {
    it('未登录会员点结算时先弹出选择层，不会立刻下单', () => {
      const { state, checkout } = setup()

      checkout.goCheckout()

      expect(createOrder).not.toHaveBeenCalled()
      expect(state.showMemberCheckoutChoice.value).toBe(true)
    })

    it('已经登录会员的顾客点结算，跳过选择层直接走原有下单流程', async () => {
      const { state, checkout } = setup({ isCustomerLoggedIn: ref(true) })
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      checkout.goCheckout()
      await vi.waitFor(() => expect(createOrder).toHaveBeenCalled())

      expect(state.showMemberCheckoutChoice.value).toBe(false)
      expect(joinByEntranceCode).not.toHaveBeenCalled()
    })

    it('已经有待支付订单要恢复时，不弹选择层，直接走支付恢复', async () => {
      const { state, checkout } = setup()
      state.pendingOrderId.value = 'order_1'
      getOrderStatus.mockResolvedValue({ data: {} })
      createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'pending' } })

      checkout.goCheckout()
      await vi.waitFor(() => expect(createWxPayOrder).toHaveBeenCalled())

      expect(state.showMemberCheckoutChoice.value).toBe(false)
      expect(createOrder).not.toHaveBeenCalled()
    })
  })

  describe('CASE 2: guest 选择直接支付', () => {
    it('点"直接支付"走原有匿名下单，不触发会员加入', async () => {
      const { state, checkout, callbacks } = setup()
      state.showMemberCheckoutChoice.value = true
      createOrder.mockResolvedValue({ data: { id: 'order_1', order_no: 'ON1', need_payment: false } })

      checkout.checkoutAsGuest()
      await vi.waitFor(() => expect(createOrder).toHaveBeenCalledTimes(1))

      expect(joinByEntranceCode).not.toHaveBeenCalled()
      expect(callbacks.bindCurrentDiningParticipant).not.toHaveBeenCalled()
      expect(state.showMemberCheckoutChoice.value).toBe(false)
    })
  })

  describe('CASE 3 / CASE 7: guest 选择加入会员', () => {
    it('加入会员成功后刷新券、选中最优券，再冻结提交并下单', async () => {
      const { state, checkout, callbacks } = setup()
      state.showMemberCheckoutChoice.value = true
      joinByEntranceCode.mockResolvedValue({ code: 200, data: { token: 'member_token' } })
      // 模拟 refreshAvailableCoupons 拉到新券后选中的最优券
      callbacks.refreshAvailableCoupons.mockImplementation(() => {
        state.selectedCouponId.value = 'best_coupon'
        return Promise.resolve()
      })
      createOrder.mockResolvedValue({ data: { id: 'order_1', order_no: 'ON1', need_payment: false } })

      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(saveCustomerSession).toHaveBeenCalledWith({ token: 'member_token' })
      expect(callbacks.bindCurrentDiningParticipant).toHaveBeenCalledTimes(1)
      expect(callbacks.refreshCustomerAuthState).toHaveBeenCalledTimes(1)
      expect(callbacks.refreshAvailableCoupons).toHaveBeenCalledWith({ required: true, forceBest: true })
      expect(state.showMemberCheckoutChoice.value).toBe(false)
      expect(createOrder).toHaveBeenCalledTimes(1)
      // CASE 7: 冻结提交时 payload 里的 coupon_id 必须已经是 join 后选中的最优券。
      expect(createOrder).toHaveBeenCalledWith(
        expect.objectContaining({ coupon_id: 'best_coupon' }),
        expect.anything()
      )
    })

    it('coupon refresh 必须发生在 join 之后（顺序断言，不是同时发生）', async () => {
      const { checkout, callbacks } = setup()
      const callOrder = []
      callbacks.bindCurrentDiningParticipant.mockImplementation(() => { callOrder.push('bind'); return Promise.resolve() })
      callbacks.refreshAvailableCoupons.mockImplementation(() => { callOrder.push('refresh_coupons'); return Promise.resolve() })
      joinByEntranceCode.mockImplementation(() => { callOrder.push('join'); return Promise.resolve({ code: 200, data: {} }) })
      createOrder.mockImplementation(() => { callOrder.push('create_order'); return Promise.resolve({ data: { id: 'order_1', need_payment: false } }) })

      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(callOrder).toEqual(['join', 'bind', 'refresh_coupons', 'create_order'])
    })
  })

  describe('CASE 5: 授权取消/拒绝', () => {
    it('没有拿到手机号授权码时不下单、购物车不受影响，仍停留在选择层', async () => {
      const { state, checkout } = setup()
      state.showMemberCheckoutChoice.value = true

      await checkout.joinMemberAndCheckout({ detail: {} })

      expect(createOrder).not.toHaveBeenCalled()
      expect(joinByEntranceCode).not.toHaveBeenCalled()
      expect(state.cart.value).toEqual({ dish_1: 1 })
      expect(state.showMemberCheckoutChoice.value).toBe(true)
    })

    it('点击取消选择层：不下单、不清空购物车，回到购物车确认单', () => {
      const { state, checkout } = setup()
      state.showMemberCheckoutChoice.value = true

      checkout.cancelMemberCheckoutChoice()

      expect(state.showMemberCheckoutChoice.value).toBe(false)
      expect(state.cart.value).toEqual({ dish_1: 1 })
      expect(createOrder).not.toHaveBeenCalled()
    })
  })

  describe('CASE 6: 加入会员网络失败', () => {
    it('joinByEntranceCode 网络异常时不下单、不清空购物车，可以重试或改直接支付', async () => {
      const { state, checkout } = setup()
      state.showMemberCheckoutChoice.value = true
      joinByEntranceCode.mockRejectedValue(new Error('network error'))

      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(createOrder).not.toHaveBeenCalled()
      expect(state.cart.value).toEqual({ dish_1: 1 })
      expect(state.showMemberCheckoutChoice.value).toBe(true)
      expect(state.memberChoiceJoining.value).toBe(false)
    })

    it('加入会员业务失败（code!=200）时提示错误，不下单', async () => {
      const { state, checkout } = setup()
      state.showMemberCheckoutChoice.value = true
      joinByEntranceCode.mockResolvedValue({ code: 400, msg: '手机号已注册' })

      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(createOrder).not.toHaveBeenCalled()
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '手机号已注册' })
      )
    })
  })

  describe('P0-9: 已有待支付订单时不允许会员流程改价', () => {
    it('joinMemberAndCheckout 发现已有 pendingOrderId 时直接放弃，绝不重新定价旧订单', async () => {
      const { state, checkout, callbacks } = setup()
      state.pendingOrderId.value = 'order_existing'
      state.showMemberCheckoutChoice.value = true

      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(joinByEntranceCode).not.toHaveBeenCalled()
      expect(callbacks.refreshAvailableCoupons).not.toHaveBeenCalled()
      expect(state.showMemberCheckoutChoice.value).toBe(false)
    })
  })

  describe('P0-A pre-cert: member / guest 并发互斥', () => {
    it('CASE CONCURRENCY-A: member join in flight 时 direct pay 不创建订单', async () => {
      const { checkout } = setup()
      let releaseJoin
      joinByEntranceCode.mockImplementation(() => new Promise((resolve) => {
        releaseJoin = () => resolve({ code: 200, data: { token: 'member_token' } })
      }))
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      const memberRun = checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })
      await vi.waitFor(() => expect(joinByEntranceCode).toHaveBeenCalledTimes(1))
      checkout.checkoutAsGuest()

      expect(createOrder).not.toHaveBeenCalled()
      releaseJoin()
      await memberRun
      expect(createOrder).toHaveBeenCalledTimes(1)
    })

    it('CASE CONCURRENCY-B: direct pay 已开始时 member join 不运行', async () => {
      const { checkout } = setup()
      let releaseOrder
      createOrder.mockImplementation(() => new Promise((resolve) => {
        releaseOrder = () => resolve({ data: { id: 'order_1', need_payment: false } })
      }))

      checkout.checkoutAsGuest()
      await vi.waitFor(() => expect(createOrder).toHaveBeenCalledTimes(1))
      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(joinByEntranceCode).not.toHaveBeenCalled()
      releaseOrder()
      await vi.waitFor(() => expect(createOrder).toHaveBeenCalledTimes(1))
    })

    it('CASE CONCURRENCY-C: double member click 只 join 一次、只创建一张订单', async () => {
      const { checkout } = setup()
      let releaseJoin
      joinByEntranceCode.mockImplementation(() => new Promise((resolve) => {
        releaseJoin = () => resolve({ code: 200, data: { token: 'member_token' } })
      }))
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      const first = checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })
      const second = checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_2' } })
      await vi.waitFor(() => expect(joinByEntranceCode).toHaveBeenCalledTimes(1))
      releaseJoin()
      await Promise.all([first, second])

      expect(joinByEntranceCode).toHaveBeenCalledTimes(1)
      expect(createOrder).toHaveBeenCalledTimes(1)
    })
  })

  describe('P0-A pre-cert: stale customer token recovery', () => {
    it('definitive auth rejection 清理旧 intent，重新授权刷新券后仅用新券创建一张订单', async () => {
      const { state, checkout, callbacks } = setup({ isCustomerLoggedIn: ref(true) })
      state.selectedCouponId.value = 'stale_coupon'
      const authError = new Error('NEED_LOGIN')
      authError.statusCode = 401
      authError.code = 'NEED_LOGIN'
      createOrder
        .mockRejectedValueOnce(authError)
        .mockResolvedValueOnce({ data: { id: 'order_1', order_no: 'ON1', need_payment: false } })
      joinByEntranceCode.mockResolvedValue({ code: 200, data: { token: 'fresh_member_token' } })
      callbacks.refreshAvailableCoupons.mockImplementation(() => {
        state.selectedCouponId.value = 'fresh_coupon'
        return Promise.resolve()
      })

      const firstOk = await checkout.submitOrder()
      const staleRequestId = createOrder.mock.calls[0][0].request_id
      expect(firstOk).toBe(false)
      expect(state.showCheckoutAuth.value).toBe(true)
      expect(state.cart.value).toEqual({ dish_1: 1 })
      expect(restorePendingSubmitIntent({ tenantId: 'shop_1', tableNo: 'A01', sessionId: 'sess_1' }).status).toBe('missing')

      await checkout.handleCheckoutAuth({ detail: { code: 'phone_code_1' } })

      expect(callbacks.refreshAvailableCoupons).toHaveBeenCalledTimes(1)
      expect(createOrder).toHaveBeenCalledTimes(2)
      expect(createOrder.mock.calls[1][0]).toEqual(expect.objectContaining({
        coupon_id: 'fresh_coupon',
        request_id: expect.any(String),
      }))
      expect(createOrder.mock.calls[1][0].request_id).not.toBe(staleRequestId)
      expect(state.cart.value).toEqual({})
    })

    it('CASE UNKNOWN-A: restored UNKNOWN 遇到 auth error 后保留原 frozen intent，并以同 request_id 原 payload 重放', async () => {
      const scope = { tenantId: 'shop_1', tableNo: 'A01', sessionId: 'sess_1' }
      const frozenSnapshot = {
        table: 'A01',
        shop: 'shop_1',
        total: 20,
        remark: '少盐',
        coupon_id: 'COUPON_OLD',
        dining_session_id: 'sess_1',
        items: [{ dish_id: 'dish_1', name: '招牌炒饭', price: 20, qty: 1 }],
      }
      expect(savePendingSubmitIntent({ ...scope, requestId: 'REQ_ORIGINAL', snapshot: frozenSnapshot })).toBe(true)
      const { state, checkout, callbacks } = setup({ isCustomerLoggedIn: ref(true) })
      const authError = new Error('NEED_LOGIN')
      authError.statusCode = 401
      authError.code = 'NEED_LOGIN'
      createOrder
        .mockRejectedValueOnce(authError)
        .mockResolvedValueOnce({ data: { id: 'order_original', order_no: 'ORIGINAL', need_payment: false } })
      joinByEntranceCode.mockResolvedValue({ code: 200, data: { token: 'fresh_member_token', coupon: { id: 'COUPON_NEW' } } })
      callbacks.refreshAvailableCoupons.mockImplementation(() => {
        state.selectedCouponId.value = 'COUPON_NEW'
        return Promise.resolve()
      })

      expect(await checkout.submitOrder()).toBe(false)
      const preserved = restorePendingSubmitIntent(scope)
      expect(preserved.status).toBe('found')
      expect(preserved.record.requestId).toBe('REQ_ORIGINAL')
      expect(preserved.record.snapshot).toEqual(frozenSnapshot)
      expect(state.pendingSubmitRequestId.value).toBe('REQ_ORIGINAL')

      await checkout.handleCheckoutAuth({ detail: { code: 'phone_code_1' } })

      expect(callbacks.refreshAvailableCoupons).not.toHaveBeenCalled()
      expect(createOrder).toHaveBeenCalledTimes(2)
      expect(createOrder.mock.calls.map(([payload]) => payload.request_id)).toEqual(['REQ_ORIGINAL', 'REQ_ORIGINAL'])
      expect(createOrder.mock.calls[1][0]).toEqual(expect.objectContaining(frozenSnapshot))
      expect(createOrder.mock.calls[1][0].coupon_id).toBe('COUPON_OLD')
    })

    it('CASE COUPON-B: join 后 required refresh 失败不建单，下次结算重试成功后只用最优券建一单', async () => {
      const { state, checkout, callbacks } = setup()
      state.showMemberCheckoutChoice.value = true
      state.remark.value = '不要辣'
      state.selectedCouponId.value = 'A'
      joinByEntranceCode.mockResolvedValue({ code: 200, data: { token: 'member_token' } })
      callbacks.refreshAvailableCoupons
        .mockRejectedValueOnce(new Error('会员权益加载失败，请重试'))
        .mockImplementationOnce(() => {
          state.selectedCouponId.value = 'B'
          return Promise.resolve()
        })
      createOrder.mockResolvedValue({ data: { id: 'order_1', order_no: 'ON1', need_payment: false } })

      await checkout.joinMemberAndCheckout({ detail: { code: 'phone_code_1' } })

      expect(createOrder).not.toHaveBeenCalled()
      expect(restorePendingSubmitIntent({ tenantId: 'shop_1', tableNo: 'A01', sessionId: 'sess_1' }).status).toBe('missing')
      expect(state.cart.value).toEqual({ dish_1: 1 })
      expect(state.remark.value).toBe('不要辣')
      expect(state.memberCheckoutBenefitsNeedRefresh.value).toBe(true)

      state.isCustomerLoggedIn.value = true
      checkout.goCheckout()
      await vi.waitFor(() => expect(createOrder).toHaveBeenCalledTimes(1))

      expect(callbacks.refreshAvailableCoupons).toHaveBeenCalledTimes(2)
      expect(callbacks.refreshAvailableCoupons).toHaveBeenNthCalledWith(2, { required: true, forceBest: true })
      expect(createOrder.mock.calls[0][0].coupon_id).toBe('B')
      expect(state.memberCheckoutBenefitsNeedRefresh.value).toBe(false)
    })

    it('join 已成功但 required refresh 待完成时，直接支付入口也不能绕过权益解析', async () => {
      const { state, checkout, callbacks } = setup({ isCustomerLoggedIn: ref(true) })
      state.memberCheckoutBenefitsNeedRefresh.value = true
      state.showMemberCheckoutChoice.value = true
      callbacks.refreshAvailableCoupons.mockRejectedValue(new Error('会员权益加载失败，请重试'))
      createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

      checkout.checkoutAsGuest()
      await vi.waitFor(() => expect(callbacks.refreshAvailableCoupons).toHaveBeenCalledWith({ required: true, forceBest: true }))

      expect(createOrder).not.toHaveBeenCalled()
      expect(state.memberCheckoutBenefitsNeedRefresh.value).toBe(true)
      expect(state.cart.value).toEqual({ dish_1: 1 })
    })
  })
})
