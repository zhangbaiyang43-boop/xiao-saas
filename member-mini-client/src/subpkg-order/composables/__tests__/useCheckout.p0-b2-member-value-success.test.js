import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { useCheckout } from '../useCheckout.js'
import { createWxPayOrder, getOrderStatus } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

// P0-B2a: 成功页会员价值/奖励券唯一 authority 是 GET /v1/orders/my 的
// member_value——这份文件只覆盖 P0-B2 审计发现的那几个具体 gap：
//   1. 正常微信支付 data 里已经带 member_value，却被整段丢弃（未消费）；
//   2. 欢迎券被当成"本单支付奖励"回退展示，reward_coupon_status=none/unknown
//      时旧值还留在屏幕上（false attribution）；
//   3. free 订单的 pay 响应没有 member_value，需要一次补充查询，且这次查询
//      的成败/时序不能反过来影响已经成立的支付成功结果；
//   4. 跨订单：上一单延迟到达的补充查询结果不能覆盖当前正在展示的下一单。
// 其余"支付成功进入成功页/免单/取消/授权失效"这些既有合同仍然只在
// useCheckout.test.js 里维护，这里不重复覆盖。

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
    successMemberValue: ref(null),
    showCheckoutAuth: ref(false),
    authorizing: ref(false),
    authActionStatus: ref('idle'),
    pendingPaymentIntent: ref(null),
    paying: ref(false),
    paymentFailed: ref(false),
    paymentConfirming: ref(false),
    paymentResultUnknown: ref(false),
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
  const merged = { ...state, ...callbacks, ...overrides }
  const checkout = useCheckout(merged)
  return { state, callbacks, checkout }
}

describe('useCheckout — P0-B2a member value / reward authority', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  it('known none：reward_coupon_status=none 清空上一单/欢迎券残留的 earnedCoupon，不回退展示', async () => {
    const { state, checkout } = setup()
    // 模拟屏幕上还留着上一单（或欢迎券兜底）的旧奖励券。
    state.earnedCoupon.value = { couponId: 'stale_welcome', amount: 8, name: '新人优惠券' }
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status: 'available', member_savings: 0, points_earned: 12, points_balance: 40,
      reward_coupon_status: 'none', reward_coupon: null,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
    expect(state.successMemberValue.value).toEqual(memberValue)
  })

  it('unknown：reward_coupon_status=unknown 同样清空 earnedCoupon，不展示奖励券也不做否定承诺', async () => {
    const { state, checkout } = setup()
    state.earnedCoupon.value = { couponId: 'stale_welcome', amount: 8, name: '新人优惠券' }
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status: 'available', member_savings: 5, points_earned: 10, points_balance: 20,
      reward_coupon_status: 'unknown', reward_coupon: null,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
    expect(state.successMemberValue.value).toEqual(memberValue)
  })

  it('not_applicable（guest）：不产生任何奖励券认领', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status: 'not_applicable', member_savings: null, points_earned: null, points_balance: null,
      reward_coupon_status: 'unknown', reward_coupon: null,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
    expect(state.successMemberValue.value.status).toBe('not_applicable')
  })

  it('unavailable：支付成功依然成立（showSuccess=true），但不产生奖励券认领、不伪造数值', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status: 'unavailable', member_savings: null, points_earned: null, points_balance: null,
      reward_coupon_status: 'unknown', reward_coupon: null,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.showSuccess.value).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
    expect(state.successMemberValue.value.status).toBe('unavailable')
  })

  it('合法的 0 值（真的没省钱/没积分）原样保留，不被当成 unavailable 或被丢弃', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status: 'available', member_savings: 0, points_earned: 0, points_balance: 100,
      reward_coupon_status: 'none', reward_coupon: null,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.successMemberValue.value).toEqual(memberValue)
  })

  // P0-B2a review fix: member_value.status 是总 authority，reward_coupon_status
  // 只在 status === 'available' 时才有意义——status 不是 available 时，即使
  // reward_coupon_status 恰好是 'issued' 并带着真实券对象，也绝不能构造
  // earnedCoupon，因为这笔订单本身的会员事实还没有被判定为可信。
  const issuedRewardCoupon = { id: 'coupon_9', amount: 5, min_amount: 20, expired_at: '2026-09-01T00:00:00', name: '专属券' }

  it.each([
    ['unavailable', 'unavailable'],
    ['pending', 'pending'],
    ['not_applicable', 'not_applicable'],
  ])('status=%s 时即使 reward_coupon_status=issued 且带真实券对象，earnedCoupon 也必须是 null', async (_label, status) => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status, member_savings: null, points_earned: null, points_balance: null,
      reward_coupon_status: 'issued', reward_coupon: issuedRewardCoupon,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.earnedCoupon.value).toBe(null)
    expect(state.successMemberValue.value.status).toBe(status)
  })

  it('status=available 且 reward_coupon_status=issued 且带真实券对象时，earnedCoupon 必须使用服务端券', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    state.payAmount.value = 20
    const memberValue = {
      status: 'available', member_savings: 5, points_earned: 81, points_balance: 326,
      reward_coupon_status: 'issued', reward_coupon: issuedRewardCoupon,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'paid', member_value: memberValue } })
    createWxPayOrder.mockResolvedValue({
      data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } },
    })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.earnedCoupon.value).toEqual(expect.objectContaining({
      couponId: 'coupon_9', amount: 5, threshold: 20, name: '专属券',
    }))
  })

  it('free 订单：成功页立即打开（不等会员价值），随后精确发起一次补充查询拿到权威 member_value', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    const memberValue = {
      status: 'available', member_savings: 3, points_earned: 5, points_balance: 10,
      reward_coupon_status: 'none', reward_coupon: null,
    }
    getOrderStatus
      .mockResolvedValueOnce({ data: {} }) // recoverPendingPaymentResult 预检查
      .mockResolvedValueOnce({ data: { status: 'done', payment_status: 'paid', member_value: memberValue } }) // 补充查询
    createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'done' } })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.showSuccess.value).toBe(true)
    // 免单响应本身没有 member_value——成功页先以"暂无会员价值"打开。
    expect(state.successMemberValue.value).toBe(null)

    await vi.waitFor(() => expect(getOrderStatus).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(state.successMemberValue.value).toEqual(memberValue))
  })

  it('free 订单补充查询网络失败：支付成功页不受影响，会员价值保持安全空态，不回退欢迎券', async () => {
    const { state, checkout } = setup()
    state.pendingOrderId.value = 'order_1'
    getOrderStatus
      .mockResolvedValueOnce({ data: {} })
      .mockRejectedValueOnce(new Error('network error'))
    createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'done' } })

    const ok = await checkout.confirmPay()

    expect(ok).toBe(true)
    expect(state.showSuccess.value).toBe(true)

    await vi.waitFor(() => expect(getOrderStatus).toHaveBeenCalledTimes(2))
    expect(state.successMemberValue.value).toBe(null)
    expect(state.earnedCoupon.value).toBe(null)
    expect(state.showSuccess.value).toBe(true)
  })

  it('跨订单：order A 延迟到达的 free 补充查询结果，不能覆盖已经是当前成功页的 order B', async () => {
    const { state, checkout } = setup()
    let resolveA
    const memberValueA = {
      status: 'available', member_savings: 99, points_earned: 999, points_balance: 999,
      reward_coupon_status: 'issued',
      reward_coupon: { id: 'coupon_A', amount: 99, min_amount: 0, expired_at: '2026-09-01T00:00:00', name: 'A单专属券' },
    }
    const memberValueB = {
      status: 'available', member_savings: 2, points_earned: 30, points_balance: 60,
      reward_coupon_status: 'none', reward_coupon: null,
    }

    getOrderStatus
      .mockResolvedValueOnce({ data: {} }) // A: recoverPendingPaymentResult 预检查
      .mockImplementationOnce(() => new Promise((resolve) => { resolveA = resolve })) // A: 补充查询——故意挂起
      .mockResolvedValueOnce({ data: {} }) // B: recoverPendingPaymentResult 预检查
      .mockResolvedValueOnce({ data: { status: 'done', payment_status: 'paid', member_value: memberValueB } }) // B: 支付确认

    createWxPayOrder
      .mockResolvedValueOnce({ data: { free: true, status: 'done' } }) // A: 免单
      .mockResolvedValueOnce({ data: { pay_params: { timeStamp: '1', nonceStr: 'n', package: 'p', paySign: 's' } } }) // B: 正常微信支付

    // --- Order A：免单成功，触发补充查询但先不 resolve ---
    state.pendingOrderId.value = 'order_A'
    const okA = await checkout.confirmPay()
    expect(okA).toBe(true)
    expect(state.orderId.value).toBe('order_A')
    expect(state.successMemberValue.value).toBe(null)

    // --- Order B：A 的补充查询还没回来，顾客已经完成了另一单支付 ---
    state.pendingOrderId.value = 'order_B'
    const okB = await checkout.confirmPay()
    expect(okB).toBe(true)
    expect(state.orderId.value).toBe('order_B')
    expect(state.successMemberValue.value).toEqual(memberValueB)

    // --- A 的延迟响应这时候才回来 ---
    resolveA({ data: { status: 'done', payment_status: 'paid', member_value: memberValueA } })
    await new Promise((resolve) => setTimeout(resolve, 0))

    // B 仍然是当前成功页，不能被 A 的迟到结果覆盖。
    expect(state.orderId.value).toBe('order_B')
    expect(state.successMemberValue.value).toEqual(memberValueB)
    expect(state.earnedCoupon.value).toBe(null)
  })
})

describe('P0-B2a static contract：结算前预计积分与支付后实际积分互不越界', () => {
  it('useCheckout.js 从不引用 expectedOrderPoints（结算前预计与支付后实际完全隔离）', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../useCheckout.js'), 'utf8')
    expect(source).not.toContain('expectedOrderPoints')
  })

  it('PaymentSuccessSheet.vue 从不引用 expectedOrderPoints 或结算期倍率字段', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../../components/PaymentSuccessSheet.vue'), 'utf8')
    expect(source).not.toContain('expectedOrderPoints')
    expect(source).not.toContain('pointMultiplier')
  })
})

describe('PaymentSuccessSheet 会员价值渲染合同（source contract，不引入组件挂载依赖）', () => {
  const readComponentSource = () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    return fs.readFileSync(path.resolve(here, '../../components/PaymentSuccessSheet.vue'), 'utf8')
  }

  it('只有 memberValue.status === available 才可能展示会员价值区', () => {
    const source = readComponentSource()
    expect(source).toContain("memberValue && memberValue.status === 'available'")
  })

  it('savings/points 分别按 >0 才展示，不展示"0积分/¥0"这类伪装成真实结果的空值', () => {
    const source = readComponentSource()
    expect(source).toContain('memberValue.member_savings > 0')
    expect(source).toContain('memberValue.points_earned > 0')
  })

  it('金额展示复用现有 formatPrice，不在组件里另写financial rounding', () => {
    const source = readComponentSource()
    expect(source).toContain('formatPrice(memberValue.member_savings)')
  })

  it('组件本身不请求 API、不读取/写入 storage、不做支付 authority 判断（纯展示）', () => {
    const source = readComponentSource()
    expect(source).not.toMatch(/uni\.request|getOrderStatus|createOrder|createWxPayOrder/)
    expect(source).not.toMatch(/uni\.(get|set|remove)StorageSync/)
  })

  it('reward 卡片结构未变（P0-B2a 只换 authority，不做视觉重构）', () => {
    const source = readComponentSource()
    expect(source).toContain('earned-coupon-card')
    expect(source).toContain('v-if="earnedCoupon"')
  })
})
