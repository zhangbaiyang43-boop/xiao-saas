import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

// P0-15-01: create-order's idempotency key (pendingSubmitRequestId) previously
// lived only in an in-memory Vue ref, page-instance-scoped. If the app process
// was killed after the create-order request was sent but before the response
// arrived, reopening the app built a brand-new useCheckout() instance with a
// fresh empty ref -- the retry then minted a NEW request_id, and the server's
// (tenant_id, client_request_id) idempotency (P0-04) has no way to recognize
// it as the same business intent, producing a genuine duplicate Order.
//
// Fix: persist the request_id (scoped by tenant+table+dining_session_id, same
// discipline as the existing pending-payment cache, P0-10) to uni storage
// BEFORE the create-order request is sent. ensureSubmitRequestId() restores
// from that storage first when the in-memory ref is empty.

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

// A genuine network/timeout failure, as produced by api/request.js's `fail:`
// branch: a bare Error with NO statusCode/code/bizCode (those are only ever
// set on a real HTTP response). This is the exact shape used to distinguish
// "ambiguous, outcome unknown" from a definitive business rejection.
function networkError() {
  return new Error('网络不稳定，请检查网络后再试')
}

function definitiveRejection(msg = '价格已更新，请重新确认:宫保鸡丁') {
  const err = new Error(msg)
  err.statusCode = 400
  err.code = 400
  return err
}

function newState(overrides = {}) {
  const cartItem = { id: 'dish_1', name: '宫保鸡丁', price: 28, qty: 1, orderName: '宫保鸡丁' }
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
    totalPrice: ref(28), cartItems: ref([cartItem]), finalPrice: ref(28), wechatPayAmount: ref(28),
    isPrepayMode: ref(true), canSubmitOrder: ref(true),
    orderSuccessTemplateId: ref('tmpl-order-success'), pickupReminderTemplateId: ref('tmpl-pickup'),
    ...overrides,
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
    clearDiningSessionStorage: vi.fn(),
  }
  const merged = { ...state, ...callbacks }
  const checkout = useCheckout(merged)
  return { state, checkout, callbacks }
}

describe('P0-15-01: durable create-order submit intent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  // ---- T03: fresh mount (process restart) must restore the SAME request_id ----
  it('T03: a brand-new useCheckout instance in the same tenant/table/session reuses the pending request_id after an ambiguous first attempt, instead of minting a new one', async () => {
    // "Mount #1" -- user taps submit, request reaches the server (or not --
    // either way the client only sees an ambiguous network failure).
    const mount1 = newState()
    createOrder.mockRejectedValueOnce(networkError())
    await mount1.checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id
    expect(firstRequestId).toBeTruthy()

    // Process is killed here -- mount1's in-memory refs (including
    // pendingSubmitRequestId) are gone. "Mount #2" is a brand-new page
    // instance: brand-new refs, same tenant/table/dining_session_id.
    const mount2 = newState()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })
    await mount2.checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id

    expect(secondRequestId).toBe(firstRequestId)
  })

  // ---- T04: a genuinely different dining_session_id must NOT reuse the old id ----
  it('T04: a fresh mount under a DIFFERENT dining_session_id never reuses the previous session\'s pending request_id', async () => {
    const mount1 = newState({ diningSessionId: ref('sess_1') })
    createOrder.mockRejectedValueOnce(networkError())
    await mount1.checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id

    // Table turned over to a new guest generation -- new dining_session_id.
    const mount2 = newState({ diningSessionId: ref('sess_2') })
    createOrder.mockResolvedValueOnce({ data: { id: 'order_2', need_payment: false, status: 'pending' } })
    await mount2.checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id

    expect(secondRequestId).not.toBe(firstRequestId)
  })

  // ---- T05: server-confirmed success clears the durable pending submit intent ----
  it('T05: once an order is server-confirmed, a subsequent fresh mount under the same scope mints a genuinely new id (no stale replay of a resolved intent)', async () => {
    const mount1 = newState()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })
    await mount1.checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id
    expect(mount1.state.pendingSubmitRequestId.value).toBe('') // cleared by _handlePaySuccess

    // A fresh mount, same scope, starting a genuinely NEW order (e.g. the
    // customer orders again later in the same session).
    const mount2 = newState()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_2', need_payment: false, status: 'pending' } })
    await mount2.checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id

    expect(secondRequestId).not.toBe(firstRequestId)
  })

  // ---- T06: a definitive (non-ambiguous) rejection still allows exactly one order on retry ----
  it('T06: after a definitive business rejection (no order created), retrying (same or fresh mount) still produces exactly one order', async () => {
    const mount1 = newState()
    createOrder.mockRejectedValueOnce(definitiveRejection())
    const firstResult = await mount1.checkout.performSubmitOrder()
    expect(firstResult).toBe(false)

    // Same page instance, user fixes the cart and retries.
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })
    const secondResult = await mount1.checkout.performSubmitOrder()
    expect(secondResult).toBe(true)
    expect(createOrder).toHaveBeenCalledTimes(2)
  })

  // ---- T09: ambiguous (network/timeout) failure shows an "unknown", not a definitive-failure, toast ----
  it('T09: a network/timeout failure during submit shows the ambiguous-outcome copy, not a definitive "submit failed" message', async () => {
    const { checkout } = newState()
    createOrder.mockRejectedValueOnce(networkError())

    await checkout.performSubmitOrder()

    expect(uni.showToast).toHaveBeenCalledTimes(1)
    const title = uni.showToast.mock.calls[0][0].title
    expect(title).not.toMatch(/下单失败/)
    expect(title).toMatch(/待确认/)
  })
})
