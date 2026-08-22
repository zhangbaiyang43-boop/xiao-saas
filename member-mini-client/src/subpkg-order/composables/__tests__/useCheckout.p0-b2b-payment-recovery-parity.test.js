import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { useCheckout } from '../useCheckout.js'
import { getOrderStatus, createWxPayOrder } from '@/api/order'

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

// P0-B2b：同一份"这笔已支付订单最终提交时长什么样"的快照，同时喂给
// cartItems（当前购物车）和 successItems（提交时的快照）——两边字段结构必须
// 完全一致，恢复对账才能靠指纹判断"购物车有没有被改过"。
const submittedItem = { id: 'dish_1', name: '招牌炒饭', orderName: '招牌炒饭', price: 20, qty: 1 }

function setup(overrides = {}) {
  const state = {
    shopId: ref('shop_1'),
    tableNo: ref('A01'),
    diningSessionId: ref('sess_1'),
    diningParticipantToken: ref('tok_1'),
    diningClientId: ref('client_1'),
    orderNo: ref('1234'),
    orderId: ref(''),
    orderStatus: ref('pending'),
    successItems: ref([{ ...submittedItem }]),
    successTotal: ref(20),
    successDiscount: ref(0),
    successMemberValue: ref(null),
    showCheckoutAuth: ref(false),
    authorizing: ref(false),
    authActionStatus: ref('idle'),
    pendingPaymentIntent: ref(null),
    paying: ref(false),
    paymentFailed: ref(false),
    paymentConfirming: ref(false),
    paymentResultUnknown: ref(false),
    payAmount: ref(20),
    pendingOrderId: ref('order_1'),
    pendingSubmitRequestId: ref(''),
    myOrders: ref([]),
    showOrders: ref(false),
    showCart: ref(true),
    showSuccess: ref(false),
    successPreserveDraft: ref(false),
    ordering: ref(false),
    tableSessionClosed: ref(false),
    paymentMode: ref('prepay'),
    reminderRequested: ref(false),
    earnedCoupon: ref(null),
    // 默认购物车跟 successItems 里的快照是同一份东西（同一个订单还没被
    // 后续操作动过），覆盖测试按需改成"已经变化"。
    cart: ref({ dish_1: 1 }),
    specCartItems: ref([]),
    remark: ref(''),
    selectedCouponId: ref(null),
    totalPrice: ref(20),
    cartItems: ref([{ ...submittedItem }]),
    finalPrice: ref(20),
    wechatPayAmount: ref(20),
    isPrepayMode: ref(true),
    canSubmitOrder: ref(true),
    orderSuccessTemplateId: ref('tmpl-order-success'),
    pickupReminderTemplateId: ref('tmpl-pickup'),
    showMemberCheckoutChoice: ref(false),
    memberChoiceJoining: ref(false),
    isCustomerLoggedIn: ref(true),
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
    refreshAvailableCoupons: vi.fn(() => Promise.resolve()),
  }
  // overrides 里传入的 ref（比如自定义 cart/cartItems）必须整体替换掉默认值，
  // 而不是被下面 return 的 state 悄悄指回没被覆盖的那份默认 ref——所以这里
  // 用合并后的 merged 本身作为对外的 state，跟 useCheckout 实际用的是同一份引用。
  const merged = { ...state, ...callbacks, ...overrides }
  const checkout = useCheckout(merged)
  return { state: merged, callbacks, checkout }
}

const memberValue = {
  status: 'available',
  member_savings: 5,
  points_earned: 81,
  points_balance: 326,
  reward_coupon_status: 'issued',
  reward_coupon: { id: 'coupon_9', amount: 5, min_amount: 20, expired_at: '2026-09-01T00:00:00', name: '专属券' },
}

describe('P0-B2b: recoverPendingPaymentResult — server paid gate', () => {
  beforeEach(() => vi.clearAllMocks())

  it('本地有 pending snapshot，但服务端仍未支付：不展示成功页，不能只凭本地快照恢复成功', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'unpaid' } })

    const ok = await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(ok).toBe(false)
    expect(state.showSuccess.value).toBe(false)
    expect(state.pendingOrderId.value).toBe('order_1')
  })
})

describe('P0-B2b: presentSuccess=true — 完整成功页 parity（冷启动 / 用户主动核对）', () => {
  beforeEach(() => vi.clearAllMocks())

  it('server paid + 权威 member_value：展示成功页，successMemberValue 与服务端原样一致，earnedCoupon 来自服务端券', async () => {
    const { state, checkout, callbacks } = setup({ showCart: ref(true), showCheckoutAuth: ref(true) })
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const ok = await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(ok).toBe(true)
    expect(state.showSuccess.value).toBe(true)
    expect(state.orderId.value).toBe('order_1')
    expect(state.successMemberValue.value).toEqual(memberValue)
    expect(state.earnedCoupon.value).toEqual(expect.objectContaining({ couponId: 'coupon_9', amount: 5 }))
    expect(state.pendingOrderId.value).toBe('')
    expect(callbacks.startStatusPoll).toHaveBeenCalledWith('order_1')
    expect(state.myOrders.value).toHaveLength(1)
    expect(state.myOrders.value[0]).toEqual(expect.objectContaining({ id: 'order_1', paymentStatus: 'paid' }))
    // 确实要展示成功页时，才允许关掉购物车确认单/授权面板。
    expect(state.showCart.value).toBe(false)
    expect(state.showCheckoutAuth.value).toBe(false)
  })

  it('reward_coupon_status=none：不展示 earnedCoupon，不回退欢迎券兜底', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({
      data: { status: 'pending', payment_status: 'paid', member_value: { ...memberValue, reward_coupon_status: 'none', reward_coupon: null } },
    })

    await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(state.showSuccess.value).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
  })

  it('reward_coupon_status=unknown：同样不展示 earnedCoupon', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({
      data: { status: 'pending', payment_status: 'paid', member_value: { ...memberValue, reward_coupon_status: 'unknown', reward_coupon: null } },
    })

    await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(state.showSuccess.value).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
  })

  it('member_value.status=unavailable：支付成功依然成立，会员价值区没有数值可展示，也不产生 earnedCoupon', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({
      data: { status: 'pending', payment_status: 'paid', member_value: { status: 'unavailable' } },
    })

    const ok = await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(ok).toBe(true)
    expect(state.showSuccess.value).toBe(true)
    expect(state.successMemberValue.value).toEqual({ status: 'unavailable' })
    expect(state.earnedCoupon.value).toBe(null)
  })
})

describe('P0-B2b: presentSuccess=false — 后台泛化恢复（用户已经不在这笔支付上下文里）', () => {
  beforeEach(() => vi.clearAllMocks())

  it('server paid：myOrders 对账 + 清 pending 标记，但不强弹成功页、不碰购物车/当前 UI，只非阻塞 toast', async () => {
    const { state, checkout } = setup({ cart: ref({ dish_1: 1, dish_2: 2 }), showCart: ref(true), showCheckoutAuth: ref(true) })
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const ok = await checkout.recoverPendingPaymentResult()

    expect(ok).toBe(true)
    expect(state.pendingOrderId.value).toBe('')
    expect(state.showSuccess.value).toBe(false)
    expect(state.orderId.value).toBe('')
    expect(state.successMemberValue.value).toBe(null)
    expect(state.cart.value).toEqual({ dish_1: 1, dish_2: 2 })
    // P1-1: 用户当前可能正开着购物车确认单/授权面板做别的事情——泛化的后台
    // 恢复不能替用户关掉它们，那是只有真的要展示成功页时才允许的动作。
    expect(state.showCart.value).toBe(true)
    expect(state.showCheckoutAuth.value).toBe(true)
    expect(state.myOrders.value[0]).toEqual(expect.objectContaining({ id: 'order_1', paymentStatus: 'paid' }))
    expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '上一笔订单已支付成功' }))
  })
})

describe('P0-B2b: 恢复购物车安全 — fail-closed 指纹比对', () => {
  beforeEach(() => vi.clearAllMocks())

  it('当前购物车跟提交快照完全一致：允许按正常成功页的方式清空这份旧购物车', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(state.cart.value).toEqual({})
    expect(state.specCartItems.value).toEqual([])
    expect(state.remark.value).toBe('')
    expect(state.selectedCouponId.value).toBe(null)
    expect(state.pendingSubmitRequestId.value).toBe('')
    expect(state.successPreserveDraft.value).toBe(false)
  })

  it('购物车已经变化（追加了新商品）：禁止整体清空，标记 successPreserveDraft=true', async () => {
    const changedCart = { dish_1: 1, dish_2: 1 }
    const changedCartItems = [{ ...submittedItem }, { id: 'dish_2', name: '酸辣汤', orderName: '酸辣汤', price: 12, qty: 1 }]
    const { state, checkout } = setup({ cart: ref(changedCart), cartItems: ref(changedCartItems) })
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(state.showSuccess.value).toBe(true)
    expect(state.cart.value).toEqual(changedCart)
    expect(state.cartItems.value).toEqual(changedCartItems)
    expect(state.remark.value).toBe('')
    expect(state.successPreserveDraft.value).toBe(true)
  })

  it('购物车数量发生变化（同一个菜从 1 份变 2 份）：同样判定为已变化，禁止清空', async () => {
    const changedCart = { dish_1: 2 }
    const changedCartItems = [{ ...submittedItem, qty: 2 }]
    const { state, checkout } = setup({ cart: ref(changedCart), cartItems: ref(changedCartItems) })
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(state.cart.value).toEqual(changedCart)
    expect(state.successPreserveDraft.value).toBe(true)
  })
})

describe('P0-B2b: 幂等 / cross-order 安全', () => {
  beforeEach(() => vi.clearAllMocks())

  it('同一订单的成功页已经开着：再次恢复只是幂等刷新，不重复 unshift、不重复清购物车、不重复 toast', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    await checkout.recoverPendingPaymentResult({ presentSuccess: true })
    expect(state.myOrders.value).toHaveLength(1)

    // 支付流程已经把 pendingOrderId 清空了，模拟一次重复的、迟到的恢复调用
    // 命中同一个已经在展示的订单——重新灌回 id（restorePendingPaymentOrder
    // 在 pendingOrderId 已经非空时直接短路，不依赖本地存储里是否还有记录）。
    state.pendingOrderId.value = 'order_1'
    uni.showToast.mockClear()

    const ok = await checkout.recoverPendingPaymentResult()

    expect(ok).toBe(true)
    expect(state.myOrders.value).toHaveLength(1)
    expect(state.showSuccess.value).toBe(true)
    expect(state.orderId.value).toBe('order_1')
    // 幂等刷新走的是"已经在展示同一订单"分支，不是后台泛化 toast 分支。
    expect(uni.showToast).not.toHaveBeenCalledWith(expect.objectContaining({ title: '上一笔订单已支付成功' }))
  })

  it('不同订单：B 的成功页开着时，A 恢复到账不能覆盖 B 的成功页展示，但仍然把 A upsert 进 myOrders', async () => {
    const { state, checkout } = setup()
    state.showSuccess.value = true
    state.orderId.value = 'order_B'
    state.orderStatus.value = 'preparing'
    state.successMemberValue.value = { status: 'available', member_savings: 9, points_earned: 1, points_balance: 1, reward_coupon_status: 'none' }
    state.earnedCoupon.value = null
    state.myOrders.value = [{ id: 'order_B', orderNo: '5678', status: 'preparing', total: 30, items: [] }]

    state.pendingOrderId.value = 'order_A'
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const ok = await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(ok).toBe(true)
    // B 的成功页状态必须原封不动。
    expect(state.orderId.value).toBe('order_B')
    expect(state.successMemberValue.value).toEqual(expect.objectContaining({ member_savings: 9 }))
    expect(state.earnedCoupon.value).toBe(null)
    // A 仍然被记入订单列表、pending 标记仍然被清掉。
    expect(state.myOrders.value.find(o => o.id === 'order_A')).toEqual(expect.objectContaining({ paymentStatus: 'paid' }))
    expect(state.pendingOrderId.value).toBe('')
  })

  it('同一订单恢复两次（模拟正常确认和 onShow 恢复撞车）：myOrders 只有一条记录', async () => {
    const { state, checkout } = setup()
    getOrderStatus.mockResolvedValue({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    await checkout.recoverPendingPaymentResult({ presentSuccess: true })
    // 模拟另一路并发确认，在 pending 标记被清掉之后，又重新发现了同一个 id。
    state.pendingOrderId.value = 'order_1'
    await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(state.myOrders.value).toHaveLength(1)
  })
})

describe('P0-B2b P0: reconcileTerminalOrder 的 pending 标记清理必须 order-bound', () => {
  beforeEach(() => vi.clearAllMocks())

  it('恢复到的 terminal 订单 A 不是当前 pendingOrderId 指向的订单 B：A 的 terminal/退款对账正常完成，但绝不能清掉 B 的 pending 标记', async () => {
    const { state, checkout, callbacks } = setup()
    state.pendingOrderId.value = 'order_B'
    // 故意先脏一遍这两个字段，证明它们确实属于"B 的 pending-payment
    // state"，不会被 A 的对账动到——如果被误清，clearPendingPaymentOrder
    // 会把它们都重置回 false。
    state.paymentFailed.value = true
    state.paymentResultUnknown.value = true

    getOrderStatus.mockResolvedValueOnce({
      data: { status: 'cancelled', payment_status: 'paid', refund_required: true },
    })

    const ok = await checkout.recoverPaymentResultById('order_A', { presentSuccess: true })

    expect(ok).toBe(false) // terminal 分支本身就返回 false，跟今天行为一致
    // B 的 pending-payment 状态必须完全原样保留，一个字段都不能被 A 的对账动到。
    expect(state.pendingOrderId.value).toBe('order_B')
    expect(state.paymentFailed.value).toBe(true)
    expect(state.paymentResultUnknown.value).toBe(true)
    // A 自己的 terminal/退款对账语义必须照常完整完成。
    expect(state.myOrders.value.find((o) => o.id === 'order_A')).toEqual(expect.objectContaining({
      status: 'cancelled', paymentStatus: 'paid', refundRequired: true,
    }))
    expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({
      title: '订单已取消，付款已成功，请联系商家处理退款',
    }))
    expect(callbacks.saveMyOrders).toHaveBeenCalled()
  })

  it('恢复到的 terminal 订单就是当前 pendingOrderId 本身：仍然按原有行为清空 pending 标记', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_A'

    getOrderStatus.mockResolvedValueOnce({
      data: { status: 'cancelled', payment_status: 'unpaid' },
    })

    const ok = await checkout.recoverPaymentResultById('order_A')

    expect(ok).toBe(false)
    expect(state.pendingOrderId.value).toBe('')
  })
})

describe('P0-B2b P0-1: 真实并发 — normal confirmation 和 onShow recovery 撞车', () => {
  beforeEach(() => vi.clearAllMocks())

  it('recovery 先一步 clearPendingPaymentOrder，随后正常 confirmation 的 getOrderStatus 才返回：不能产生空 id 的订单，最终状态必须完整', async () => {
    const { state, checkout } = setup()
    createWxPayOrder.mockResolvedValue({ data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } } })

    let resolveConfirmationRead
    getOrderStatus
      // 1) confirmPay 自己的 presentSuccess:true 核对，此时还没支付。
      .mockResolvedValueOnce({ data: {} })
      // 2) requestPayment 成功后，waitForBackendPaymentConfirmation 第一次
      //    读取——故意挂起，模拟弱网/正在传输中。
      .mockImplementationOnce(() => new Promise((resolve) => { resolveConfirmationRead = resolve }))
      // 3) 与此同时单独触发的 onShow 恢复（下面手动调用），它自己的
      //    getOrderStatus 读取先一步回来，读到已支付。
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const confirmPayPromise = checkout.confirmPay()
    // 让 confirmPay 内部一路跑到 waitForBackendPaymentConfirmation 挂起的
    // 那次 getOrderStatus——中间全是已经 resolve 的 Promise 链（订阅消息/
    // wxLogin/createWxPayOrder/requestPayment），用一次宏任务把它们全部
    // 冲刷掉，比链式 await Promise.resolve() 更不依赖具体跳数。
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(resolveConfirmationRead).toBeTypeOf('function')

    // 并发的 onShow 后台恢复：抢先确认了同一笔订单已支付，并且清掉了
    // pending 标记——这正是本轮要修的竞态：如果 _handlePaySuccess 还在
    // 内部重新读 pendingOrderId.value，接下来它会读到空字符串。
    const recovered = await checkout.recoverPendingPaymentResult()
    expect(recovered).toBe(true)
    expect(state.pendingOrderId.value).toBe('')

    // 现在才放行正常确认自己的那次读取，同样返回已支付。
    resolveConfirmationRead({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    const ok = await confirmPayPromise

    expect(ok).toBe(true)
    expect(state.orderId.value).toBe('order_1')
    expect(state.showSuccess.value).toBe(true)
    expect(state.successMemberValue.value).toEqual(memberValue)
    expect(state.myOrders.value).toHaveLength(1)
    expect(state.myOrders.value[0].id).toBe('order_1')
    expect(state.myOrders.value.some((o) => o.id === '' || o.id === undefined)).toBe(false)
  })

  it('recovery 先一步 clearPendingPaymentOrder，随后 uni.requestPayment 才 resolve：整条支付链必须继续用冻结的 order_1，不能变成空 id', async () => {
    // P0-B2b P0 fix：比上一个测试更早的竞态窗口——uni.requestPayment 本身
    // 就是一次真正的异步支付动作，在它 resolve 之前，pendingOrderId 完全
    // 可能已经被并发的 onShow 恢复清空。confirmPay 冻结的 paymentOrderId
    // 必须扛住这个窗口，而不是等到 requestPayment 成功以后才去读
    // pendingOrderId.value。
    const { state, checkout } = setup()
    createWxPayOrder.mockResolvedValue({ data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } } })

    let resolvePayment
    uni.requestPayment.mockImplementationOnce(() => new Promise((resolve) => { resolvePayment = resolve }))

    getOrderStatus
      // 1) confirmPay 自己的 presentSuccess:true 核对，此时还没支付。
      .mockResolvedValueOnce({ data: {} })
      // 2) 并发触发的 onShow 恢复，读到已支付。
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
      // 3) uni.requestPayment 放行后，waitForBackendPaymentConfirmation 自己
      //    的第一次读取，同样已支付。
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const confirmPayPromise = checkout.confirmPay()
    // 冲刷 precheck / createWxPayOrder 这些已经 resolve 的 Promise 链，让
    // confirmPay 卡在 uni.requestPayment 本身。
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(resolvePayment).toBeTypeOf('function')
    expect(createWxPayOrder).toHaveBeenCalledWith('order_1', false, expect.anything())

    // 并发的 onShow 后台恢复：抢先确认已支付，清空了 pendingOrderId——
    // 此时 confirmPay 还没从 uni.requestPayment 里返回。
    const recovered = await checkout.recoverPendingPaymentResult()
    expect(recovered).toBe(true)
    expect(state.pendingOrderId.value).toBe('')

    // 现在才放行 uni.requestPayment 本身。
    resolvePayment()
    const ok = await confirmPayPromise

    expect(ok).toBe(true)
    // 支付确认必须仍然拿着 order_1 去查，不能变成用空字符串去查。
    expect(getOrderStatus).toHaveBeenCalledWith('order_1', 'tok_1')
    expect(getOrderStatus).not.toHaveBeenCalledWith('', expect.anything())
    expect(state.orderId.value).toBe('order_1')
    expect(state.showSuccess.value).toBe(true)
    expect(state.successMemberValue.value).toEqual(memberValue)
    expect(state.myOrders.value).toHaveLength(1)
    expect(state.myOrders.value[0].id).toBe('order_1')
    expect(state.myOrders.value.some((o) => o.id === '' || o.id === undefined)).toBe(false)
  })

  it('recovery 先一步 clearPendingPaymentOrder，随后 uni.requestPayment 才 reject：catch 必须用冻结的 order_1 核对服务端 truth，不能误判成支付失败', async () => {
    // P0-B2b P0 fix：本轮要修的正是这条——success path（resolve）已经在
    // 上一个测试里验证过用冻结 id，但 requestPayment 失败/reject 时走的是
    // 完全不同的 catch 分支，那里过去是直接调用会重新读 pendingOrderId.value
    // 的公开 recoverPendingPaymentResult()。如果并发恢复已经先把
    // pendingOrderId 清空了，公开函数会因为"没有 pending 订单"直接短路返回
    // false，于是 catch 继续往下走到 paymentFailed=true，把一次真实已经
    // 支付成功的订单，误判成"支付失败，请重试"。
    const { state, checkout } = setup()
    createWxPayOrder.mockResolvedValue({ data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } } })

    let rejectPayment
    uni.requestPayment.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectPayment = reject }))

    getOrderStatus
      // 1) confirmPay 自己的 presentSuccess:true 核对，此时还没支付。
      .mockResolvedValueOnce({ data: {} })
      // 2) 并发触发的 onShow 恢复，读到已支付（把 pendingOrderId 清空）。
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
      // 3) uni.requestPayment reject 后，catch 里用冻结的 order_1 再核对一
      //    次服务端 truth，同样已支付。
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const confirmPayPromise = checkout.confirmPay()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(rejectPayment).toBeTypeOf('function')

    // 并发的 onShow 后台恢复：抢先确认已支付，清空了 pendingOrderId——
    // 此时 confirmPay 还卡在 uni.requestPayment 里，什么结果都还不知道。
    const recovered = await checkout.recoverPendingPaymentResult()
    expect(recovered).toBe(true)
    expect(state.pendingOrderId.value).toBe('')

    // 现在才让 uni.requestPayment 失败——真实场景里这就是弱网/微信支付面板
    // 报错，跟这笔订单到底有没有支付成功完全是两件事。
    rejectPayment({ errMsg: 'requestPayment:fail system error' })
    const ok = await confirmPayPromise

    expect(ok).toBe(true)
    expect(state.paymentFailed.value).toBe(false)
    // catch 里的核对必须仍然拿着 order_1 去查，不能变成用空字符串去查。
    expect(getOrderStatus).toHaveBeenCalledWith('order_1', 'tok_1')
    expect(getOrderStatus).not.toHaveBeenCalledWith('', expect.anything())
    expect(state.orderId.value).toBe('order_1')
    expect(state.showSuccess.value).toBe(true)
    expect(state.successMemberValue.value).toEqual(memberValue)
    expect(state.myOrders.value).toHaveLength(1)
    expect(state.myOrders.value[0].id).toBe('order_1')
    expect(state.myOrders.value.some((o) => o.id === '' || o.id === undefined)).toBe(false)
    expect(uni.showToast).not.toHaveBeenCalledWith(expect.objectContaining({ title: expect.stringContaining('支付失败') }))
  })
})

describe('P0-B2b: 失败安全 — 不能把查询失败误判成未支付', () => {
  beforeEach(() => vi.clearAllMocks())

  it('网络异常：pendingOrderId 和本地 storage 都原样保留，cart/showSuccess 都不受影响', async () => {
    const { state, checkout } = setup({ cart: ref({ dish_1: 1, dish_2: 2 }) })
    getOrderStatus.mockRejectedValue(new Error('network error'))

    const ok = await checkout.recoverPendingPaymentResult({ presentSuccess: true })

    expect(ok).toBe(false)
    expect(state.pendingOrderId.value).toBe('order_1')
    expect(state.showSuccess.value).toBe(false)
    expect(state.cart.value).toEqual({ dish_1: 1, dish_2: 2 })
  })
})

describe('P0-B2b: 正常支付成功路径保持不变', () => {
  beforeEach(() => vi.clearAllMocks())

  it('_handlePaySuccess（正常支付）无条件清空购物车，successPreserveDraft 保持 false', async () => {
    const { state, checkout } = setup({ cart: ref({ dish_1: 1, dish_2: 2 }) })
    state.successPreserveDraft.value = true // 故意脏一个上一次恢复可能留下的状态，验证会被正常支付强制归位。
    createWxPayOrder.mockResolvedValue({ data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } } })
    // 第一次 getOrderStatus 是 confirmPay 里 presentSuccess:true 的核对
    // 前置检查（此时还没支付），第二次是 requestPayment 成功后
    // waitForBackendPaymentConfirmation 读到的服务端已支付结果。
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.showSuccess.value).toBe(true)
    expect(state.cart.value).toEqual({})
    expect(state.successPreserveDraft.value).toBe(false)
  })
})

describe('P0-B2b static contract：menu.vue 恢复触发点的 presentSuccess 语义', () => {
  const readMenuSource = () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    return fs.readFileSync(path.resolve(here, '../../pages/menu.vue'), 'utf8')
  }

  it('onLoad 冷启动恢复：presentSuccess 固定为 true', () => {
    const source = readMenuSource()
    expect(source).toMatch(/recoverPendingPaymentResult\(\{\s*showDetail:\s*options\.openOrders === '1',\s*presentSuccess:\s*true\s*\}\)/)
  })

  it('onShow 前台恢复：presentSuccess 由 paymentResultUnknown 决定，不是无条件强弹', () => {
    const source = readMenuSource()
    expect(source).toMatch(/recoverPendingPaymentResult\(\{\s*presentSuccess:\s*this\.paymentResultUnknown === true\s*\}\)/)
  })

  it('没有新增 RecoverySuccessSheet / PaymentRecoveredSheet 之类的第二套成功组件', () => {
    const source = readMenuSource()
    expect(source).not.toMatch(/RecoverySuccessSheet|PaymentRecoveredSheet|MemberRecoveryCard/)
  })

  it('finishOrdering / continueOrdering 关闭成功页时，按 successPreserveDraft 决定是否清空购物车，并且始终重置 successMemberValue/earnedCoupon/successPreserveDraft', () => {
    const source = readMenuSource()
    const finishOrderingBody = source.slice(source.indexOf('const finishOrdering ='), source.indexOf('const closeSuccessAndWait ='))
    const continueOrderingBody = source.slice(source.indexOf('const continueOrdering ='), source.indexOf('const viewOrderDetail ='))
    for (const body of [finishOrderingBody, continueOrderingBody]) {
      expect(body).toContain('successPreserveDraft.value')
      expect(body).toContain('successMemberValue.value = null')
      expect(body).toContain('earnedCoupon.value = null')
      expect(body).toContain('successPreserveDraft.value = false')
    }
  })

  it('viewOrderDetail 不清空购物车（只重置成功页状态、进入订单列表）', () => {
    const source = readMenuSource()
    const viewOrderDetailBody = source.slice(source.indexOf('const viewOrderDetail ='), source.indexOf('const remark ='))
    expect(viewOrderDetailBody).not.toContain('cart.value = {}')
    expect(viewOrderDetailBody).not.toContain('specCartItems.value = []')
    expect(viewOrderDetailBody).toContain('successPreserveDraft.value = false')
  })
})

describe('P0-B2b static contract：PaymentSuccessSheet.vue 零改动', () => {
  it('恢复流程不新增任何 recovery 专属展示逻辑（继续复用同一个成功组件）', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../../components/PaymentSuccessSheet.vue'), 'utf8')
    expect(source).not.toMatch(/recover|恢复/i)
  })
})
