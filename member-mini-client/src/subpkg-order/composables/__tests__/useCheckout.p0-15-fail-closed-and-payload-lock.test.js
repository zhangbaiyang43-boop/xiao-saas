import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

// P0-15 FINAL CLOSURE -- two gaps found on code re-review of the P0-15-01 fix
// (commit 88fdd550):
//
// Gap A (fail-open on storage failure): savePendingSubmitIntent() already
// swallows a uni.setStorageSync exception internally and returns false, but
// the caller in useCheckout.js never checked that return value before going
// ahead and sending the create-order request anyway. If durable persistence
// silently fails and the app is then killed before the response arrives, the
// request_id is unrecoverable on restart -- the exact P0-15-01 failure mode,
// just reached through a storage failure instead of a process kill.
//
// Gap B (request_id / payload drift): the durable record stores a snapshot,
// but restore only ever reused the request_id, not the frozen payload --
// retries were still built from the LIVE cart. If the cart changed between an
// ambiguous first attempt and the retry, the client would send the SAME
// request_id paired with a DIFFERENT business payload, relying entirely on
// the server's P0-04 fingerprint-conflict recovery as the only safety net
// instead of the client itself preserving "one request_id = one immutable
// business payload" (P0-04 fingerprint recovery must still be kept as the
// second line of defense -- this closure does not remove it).

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

function networkError() {
  return new Error('网络不稳定，请检查网络后再试')
}

const TENANT = 'shop_1'
const TABLE = 'A01'
const SESSION = 'sess_1'
const STORAGE_KEY = `pending_order_submit_${TENANT}_${TABLE}_${SESSION}`

function newState(overrides = {}) {
  const cartItem = { id: 'dish_1', name: '宫保鸡丁', price: 28, qty: 1, orderName: '宫保鸡丁' }
  const state = {
    shopId: ref(TENANT), tableNo: ref(TABLE), diningSessionId: ref(SESSION),
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

describe('P0-15 closure Gap A: storage write failure must fail closed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  // ---- F01 ----
  it('F01: uni.setStorageSync throwing during submit means createOrder is never called', async () => {
    uni.setStorageSync.mockImplementationOnce(() => { throw new Error('storage full') })
    const { checkout } = newState()

    const result = await checkout.performSubmitOrder()

    expect(result).toBe(false)
    expect(createOrder).not.toHaveBeenCalled()
  })

  it('F01b: the fail-closed toast is a distinct local-save message, not the ambiguous "pending confirmation" copy', async () => {
    uni.setStorageSync.mockImplementationOnce(() => { throw new Error('storage full') })
    const { checkout } = newState()

    await checkout.performSubmitOrder()

    const title = uni.showToast.mock.calls[0][0].title
    expect(title).not.toMatch(/待确认/)
    expect(title).not.toMatch(/下单失败/)
  })

  // ---- F02 ----
  it('F02: a successful storage write still allows createOrder to be called normally', async () => {
    const { checkout } = newState()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })

    const result = await checkout.performSubmitOrder()

    expect(result).toBe(true)
    expect(createOrder).toHaveBeenCalledTimes(1)
  })
})

describe('P0-15 closure Gap B: request_id always carries the SAME frozen business payload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  // ---- F03 / F05 ----
  it('F03 + F05: ambiguous first attempt, then live cart edited before retry (same page) -- retry resends the FROZEN original payload, never the edited one', async () => {
    const { state, checkout } = newState()
    createOrder.mockRejectedValueOnce(networkError())
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })

    await checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id
    const firstRemark = createOrder.mock.calls[0][0].remark

    // Live cart edited between the ambiguous attempt and the retry.
    state.remark.value = 'changed after the fact'

    await checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id
    const secondRemark = createOrder.mock.calls[1][0].remark

    expect(secondRequestId).toBe(firstRequestId)
    expect(secondRemark).toBe(firstRemark) // frozen A, never live B
    expect(secondRemark).not.toBe('changed after the fact')
  })

  // ---- F04 ----
  it('F04: ambiguous first attempt, then a genuinely fresh mount -- retry resends the SAME frozen payload and id', async () => {
    const mount1 = newState()
    createOrder.mockRejectedValueOnce(networkError())
    await mount1.checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id
    const firstRemark = createOrder.mock.calls[0][0].remark

    // Fresh mount: brand new refs, live cart differs from what was frozen.
    const mount2 = newState({ remark: ref('a totally different remark') })
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })
    await mount2.checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id
    const secondRemark = createOrder.mock.calls[1][0].remark

    expect(secondRequestId).toBe(firstRequestId)
    expect(secondRemark).toBe(firstRemark)
  })

  // ---- F06 ----
  it('F06: once the server confirms an order, the durable intent is cleared (freeing the id for a genuinely new one)', async () => {
    const { state, checkout } = newState()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })

    await checkout.performSubmitOrder()

    expect(state.pendingSubmitRequestId.value).toBe('')
    expect(uni.getStorageSync(STORAGE_KEY)).toBeFalsy()
  })

  // ---- F07 ----
  it('F07: a genuinely new order after a prior success gets a new id and its own (new) frozen payload', async () => {
    const { state, checkout } = newState()
    createOrder.mockResolvedValueOnce({ data: { id: 'order_1', need_payment: false, status: 'pending' } })
    await checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id

    state.remark.value = 'a second, unrelated order'
    createOrder.mockResolvedValueOnce({ data: { id: 'order_2', need_payment: false, status: 'pending' } })
    await checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id
    const secondRemark = createOrder.mock.calls[1][0].remark

    expect(secondRequestId).not.toBe(firstRequestId)
    expect(secondRemark).toBe('a second, unrelated order')
  })

  // ---- F08 ----
  it('F08: a fresh mount under a DIFFERENT dining_session_id never replays the previous session\'s frozen payload', async () => {
    const mount1 = newState({ diningSessionId: ref('sess_1') })
    createOrder.mockRejectedValueOnce(networkError())
    await mount1.checkout.performSubmitOrder()
    const firstRequestId = createOrder.mock.calls[0][0].request_id
    const firstRemark = createOrder.mock.calls[0][0].remark

    const mount2 = newState({ diningSessionId: ref('sess_2'), remark: ref('new generation, new order') })
    createOrder.mockResolvedValueOnce({ data: { id: 'order_2', need_payment: false, status: 'pending' } })
    await mount2.checkout.performSubmitOrder()
    const secondRequestId = createOrder.mock.calls[1][0].request_id
    const secondRemark = createOrder.mock.calls[1][0].remark

    expect(secondRequestId).not.toBe(firstRequestId)
    expect(secondRemark).toBe('new generation, new order')
    expect(secondRemark).not.toBe(firstRemark)
  })

  // ---- F09 ----
  it('F09: a corrupt durable record for the current scope fails closed -- never sends an uncertain mutation under an assumed-fresh identity', async () => {
    uni.setStorageSync(STORAGE_KEY, '{not valid json')
    const { checkout } = newState()

    const result = await checkout.performSubmitOrder()

    expect(result).toBe(false)
    expect(createOrder).not.toHaveBeenCalled()
  })
})
