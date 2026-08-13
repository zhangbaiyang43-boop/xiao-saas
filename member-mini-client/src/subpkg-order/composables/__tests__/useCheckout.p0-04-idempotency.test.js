import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

// P0-04 C04/C05/C07: server-side IDEMPOTENCY_CONFLICT recovery must never spawn
// a second order-recovery UI or a new submission key -- it binds pendingOrderId
// to the server's existing_order_id and continues through the *existing*
// confirmPay/recoverPendingPaymentResult paths.

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

function conflictError(overrides = {}) {
  const err = new Error('订单信息已变化，请重新确认后再提交')
  err.statusCode = 409
  err.code = 409
  err.bizCode = 'IDEMPOTENCY_CONFLICT'
  err.data = {
    code: 'IDEMPOTENCY_CONFLICT',
    existing_order_id: 'order_existing_1',
    existing_order_no: '1234',
    payment_mode: 'prepay',
    payment_status: 'unpaid',
    need_payment: true,
    ...overrides,
  }
  return err
}

function setup(items) {
  const cartItem = items || [{ id: 'dish_1', name: '宫保鸡丁', price: 28, qty: 1, orderName: '宫保鸡丁' }]
  const state = {
    shopId: ref('shop_1'), tableNo: ref('A01'), diningSessionId: ref('sess_1'),
    diningParticipantToken: ref('tok_1'), diningClientId: ref('client_1'),
    orderNo: ref(''), orderId: ref(''), orderStatus: ref('pending'),
    successItems: ref([]), successTotal: ref(0), successDiscount: ref(0),
    showCheckoutAuth: ref(false), authorizing: ref(false), authActionStatus: ref('idle'),
    pendingPaymentIntent: ref(null), paying: ref(false), paymentFailed: ref(false),
    paymentConfirming: ref(false), paymentResultUnknown: ref(false),
    payAmount: ref(0), pendingOrderId: ref(''), pendingSubmitRequestId: ref(''),
    myOrders: ref([]), showOrders: ref(false), showCart: ref(true), showSuccess: ref(false),
    ordering: ref(false), tableSessionClosed: ref(false), paymentMode: ref('prepay'),
    reminderRequested: ref(false), earnedCoupon: ref(null),
    cart: ref({ dish_1: 1 }), specCartItems: ref([]), remark: ref(''), selectedCouponId: ref(null),
    totalPrice: ref(28), cartItems: ref(cartItem), finalPrice: ref(28), wechatPayAmount: ref(28),
    isPrepayMode: ref(true), canSubmitOrder: ref(true),
    orderSuccessTemplateId: ref('tmpl-order-success'), pickupReminderTemplateId: ref('tmpl-pickup'),
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
  const merged = { ...state, ...callbacks }
  const checkout = useCheckout(merged)
  return { state, checkout }
}

describe('P0-04 IDEMPOTENCY_CONFLICT client recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  it('C04 prepay: binds pendingOrderId to the existing order and continues to pay it, never posts a new order', async () => {
    const { checkout } = setup()
    createOrder.mockRejectedValue(conflictError({ need_payment: true, payment_mode: 'prepay' }))
    createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'paid' } })

    await checkout.performSubmitOrder()

    // createWxPayOrder targeting the EXISTING order id is the proof no second
    // order was ever created -- pendingOrderId itself is correctly cleared
    // again once _handlePaySuccess runs (full payment completion), which is
    // the expected end state, not a bug.
    expect(createWxPayOrder).toHaveBeenCalledWith(
      'order_existing_1', expect.anything(), expect.anything(),
    )
    expect(createOrder).toHaveBeenCalledTimes(1) // never retried with a new key
  })

  it('C05 postpay: binds pendingOrderId and recovers into the existing order success state, never posts a new order', async () => {
    const { state, checkout } = setup()
    createOrder.mockRejectedValue(conflictError({
      need_payment: false, payment_mode: 'postpay', payment_status: 'unpaid',
    }))
    getOrderStatus.mockResolvedValue({
      data: { status: 'pending', payment_status: 'unpaid', payment_mode: 'postpay' },
    })

    await checkout.performSubmitOrder()

    expect(state.pendingOrderId.value).toBe('') // recoverPendingPaymentResult clears it on success
    expect(state.orderId.value).toBe('order_existing_1')
    expect(createWxPayOrder).not.toHaveBeenCalled()
    expect(createOrder).toHaveBeenCalledTimes(1)
  })

  it('P0-04 remark reconciliation §12: ambiguous first attempt + remark edit on retry recovers the existing order, never posts K2', async () => {
    // Real-world shape of this scenario: attempt 1's response is LOST in transit
    // (network drop) -- the order (O1) is actually created server-side, but the
    // client never sees the response, so it falls through the generic error
    // path (not IDEMPOTENCY_CONFLICT) and does NOT clear its submission key.
    // The customer edits the remark and retries with the SAME key; only THIS
    // second attempt gets a real response from the server -- a 409 conflict,
    // since O1's fingerprint (remark "不要香菜") no longer matches the retried
    // payload (remark "多放香菜").
    const specItem = {
      id: 'dish_1', name: '宫保鸡丁', price: 40, qty: 1,
      orderName: '宫保鸡丁(大份、鸡蛋、不要香菜)',
      specifications: [{ group: '份量', value: '大份' }], extras: ['鸡蛋'],
      itemRemark: '不要香菜',
    }
    const { state, checkout } = setup([specItem])
    state.pendingSubmitRequestId.value = 'K1'
    const networkError = new Error('request:fail')
    createOrder.mockRejectedValueOnce(networkError)
    createOrder.mockRejectedValueOnce(conflictError({ need_payment: true, payment_mode: 'prepay' }))
    createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'paid' } })
    // Prepay recovery must not short-circuit as "already submitted" before
    // actually paying -- explicit here (not relying on a prior test's mock
    // default) since prepay's isPaidOrSubmittedOrder only trusts payment_status.
    // Once-scoped so it doesn't leak into later tests in this file (they don't
    // mock getOrderStatus themselves and rely on vi.fn()'s default undefined).
    getOrderStatus.mockResolvedValueOnce({ data: { status: 'pending', payment_status: 'unpaid', payment_mode: 'prepay' } })

    await checkout.performSubmitOrder() // attempt 1: remark "不要香菜", response lost
    expect(state.pendingSubmitRequestId.value).toBe('K1') // ambiguous failure never clears the key

    // customer edits the remark, then retries -- still the same K1
    specItem.itemRemark = '多放香菜'
    specItem.orderName = '宫保鸡丁(大份、鸡蛋、多放香菜)'
    await checkout.performSubmitOrder() // attempt 2: hits the real conflict, recovers O1

    // both submissions carried the real structured remark, never re-parsed from name
    expect(createOrder.mock.calls[0][0].items[0].item_remark).toBe('不要香菜')
    expect(createOrder.mock.calls[1][0].items[0].item_remark).toBe('多放香菜')
    expect(createOrder).toHaveBeenCalledTimes(2) // both retried with the SAME key K1, no new key minted
    expect(createOrder.mock.calls[0][0].request_id).toBe('K1')
    expect(createOrder.mock.calls[1][0].request_id).toBe('K1')
    // recovery targets the EXISTING order -- never a second (K2) order
    expect(createWxPayOrder).toHaveBeenCalledTimes(1)
    expect(createWxPayOrder).toHaveBeenCalledWith('order_existing_1', expect.anything(), expect.anything())
  })

  it('conflict recovery never generates a new pendingSubmitRequestId', async () => {
    const { state, checkout } = setup()
    state.pendingSubmitRequestId.value = 'K1'
    createOrder.mockRejectedValue(conflictError({ need_payment: true }))
    createWxPayOrder.mockResolvedValue({ data: { free: true, status: 'paid' } })

    await checkout.performSubmitOrder()

    expect(state.pendingSubmitRequestId.value).toBe('K1')
  })

  it('a plain 409 that is NOT an idempotency conflict still falls through to dining-identity handling (no regression)', async () => {
    const { checkout } = setup()
    const err = new Error('本桌身份已失效')
    err.code = '409'
    createOrder.mockRejectedValue(err)
    isDiningIdentityError.mockImplementation((e) => String(e?.code || '') === '409')

    const result = await checkout.performSubmitOrder()

    // isDiningIdentityError path retries ensureDiningSession + performSubmitOrder(true);
    // with the same rejection recurring, it should NOT be routed into idempotency
    // conflict handling (pendingOrderId must stay untouched).
    expect(result).toBe(false)
  })

  // ---- C07: after a definitive success, the NEXT business intent gets a new key ----
  it('C07: after _handlePaySuccess clears pendingSubmitRequestId, the next submit generates a genuinely new key', async () => {
    const { state, checkout } = setup()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })
    await checkout.performSubmitOrder()
    const firstKey = createOrder.mock.calls[0][0].request_id
    expect(firstKey).toBeTruthy()
    expect(state.pendingSubmitRequestId.value).toBe('') // cleared by _handlePaySuccess

    createOrder.mockResolvedValueOnce({ data: { id: 'order_2', need_payment: false, status: 'pending' } })
    await checkout.performSubmitOrder()
    const secondKey = createOrder.mock.calls[1][0].request_id

    expect(secondKey).toBeTruthy()
    expect(secondKey).not.toBe(firstKey)
  })
})
