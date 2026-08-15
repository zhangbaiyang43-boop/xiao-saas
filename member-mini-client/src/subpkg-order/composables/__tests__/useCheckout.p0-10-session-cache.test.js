import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

// P0-10: pending_payment_order_<shop>_<table> must be scoped by dining_session_id
// too, not just shop+table -- otherwise a new guest generation's device (or the
// same guest's own resumed session after the table turned over) could restore a
// PREVIOUS generation's pending-payment order id into local state.

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
  const cartItem = { id: 'dish_1', name: '宫保鸡丁', price: 28, qty: 1, orderName: '宫保鸡丁' }
  const state = {
    shopId: ref('shop_1'), tableNo: ref('A01'), diningSessionId: ref('SA'),
    diningParticipantToken: ref('tok_1'), diningClientId: ref('client_1'),
    orderNo: ref(''), orderId: ref(''), orderStatus: ref('pending'),
    successItems: ref([]), successTotal: ref(0), successDiscount: ref(0),
    showCheckoutAuth: ref(false), authorizing: ref(false), authActionStatus: ref('idle'),
    pendingPaymentIntent: ref(null), paying: ref(false), paymentFailed: ref(false),
    paymentConfirming: ref(false), paymentResultUnknown: ref(false),
    payAmount: ref(28), pendingOrderId: ref(''), pendingSubmitRequestId: ref(''),
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

describe('P0-10: pending-payment cache is session-scoped', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('same shop+table, different dining_session_id (next guest generation) must not see the previous pending payment', () => {
    const { state, checkout } = setup({ diningSessionId: ref('SA') })
    state.pendingOrderId.value = 'order_a1'
    state.orderNo.value = '1234'
    state.payAmount.value = 28
    checkout.savePendingPaymentOrder()

    // next generation at the SAME physical table: same shop/table, new session
    state.diningSessionId.value = 'SB'
    state.pendingOrderId.value = ''
    const restored = checkout.restorePendingPaymentOrder()

    expect(restored).toBe(false)
    expect(state.pendingOrderId.value).toBe('')
  })

  it('restoring under the SAME session that saved it still works (regression -- not over-isolated)', () => {
    const { state, checkout } = setup({ diningSessionId: ref('SA') })
    state.pendingOrderId.value = 'order_a1'
    state.orderNo.value = '1234'
    state.payAmount.value = 28
    checkout.savePendingPaymentOrder()

    state.pendingOrderId.value = ''
    const restored = checkout.restorePendingPaymentOrder()

    expect(restored).toBe(true)
    expect(state.pendingOrderId.value).toBe('order_a1')
  })

  it('no valid dining_session_id yet: must not restore any cached pending-payment order', () => {
    const { state, checkout } = setup({ diningSessionId: ref('SA') })
    state.pendingOrderId.value = 'order_a1'
    checkout.savePendingPaymentOrder()

    state.diningSessionId.value = ''
    state.pendingOrderId.value = ''
    const restored = checkout.restorePendingPaymentOrder()

    expect(restored).toBe(false)
    expect(state.pendingOrderId.value).toBe('')
  })
})

describe('P0-10-05: unrecovered identity-invalid clears stale session cache', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('rebuild-and-retry fails to recover -> clears session storage + participant token, does not mark table closed', async () => {
    const { state, checkout, callbacks } = setup({ diningParticipantToken: ref('stale_tok') })
    isDiningIdentityError.mockReturnValue(true)
    callbacks.ensureDiningSession.mockResolvedValue(false) // rebuild itself fails
    createOrder.mockRejectedValue(Object.assign(new Error('本桌身份已失效'), { code: 409 }))

    const result = await checkout.performSubmitOrder()

    expect(result).toBe(false)
    expect(callbacks.clearDiningSessionStorage).toHaveBeenCalledTimes(1)
    expect(state.diningParticipantToken.value).toBe('')
    // deliberately NOT tableSessionClosed -- that's a different, stronger signal
    // ("本桌用餐已结束") that this generic identity-invalid case must not claim.
    expect(state.tableSessionClosed.value).toBe(false)
  })

  it('a genuinely recoverable identity error (rebuild + retry succeeds) never clears storage', async () => {
    const { state, checkout, callbacks } = setup({ diningParticipantToken: ref('will_be_refreshed') })
    isDiningIdentityError.mockReturnValue(true)
    callbacks.ensureDiningSession.mockResolvedValue(true) // rebuild succeeds
    createOrder
      .mockRejectedValueOnce(Object.assign(new Error('本桌身份已失效'), { code: 409 }))
      .mockResolvedValueOnce({ data: { id: 'order_retry', need_payment: false, status: 'pending' } })

    const result = await checkout.performSubmitOrder()

    expect(result).toBe(true)
    expect(callbacks.clearDiningSessionStorage).not.toHaveBeenCalled()
  })
})
