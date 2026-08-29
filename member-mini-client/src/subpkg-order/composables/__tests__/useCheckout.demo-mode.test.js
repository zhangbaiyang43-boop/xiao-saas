import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder } from '@/api/order'
import { joinByEntranceCode } from '@/api/auth'

vi.mock('@/api/order', () => ({
  createOrder: vi.fn(),
  createWxPayOrder: vi.fn(),
  getOrderStatus: vi.fn(),
}))
vi.mock('@/api/auth', () => ({ joinByEntranceCode: vi.fn() }))
vi.mock('@/utils/auth', () => ({
  saveCustomerSession: vi.fn(),
  clearCustomerSession: vi.fn(),
}))
vi.mock('@/utils/dining', () => ({ isDiningIdentityError: vi.fn(() => false) }))

function setup() {
  const state = {
    shopId: ref('demo-shop'),
    tableNo: ref('D01'),
    diningSessionId: ref('demo-session'),
    diningParticipantToken: ref('participant-token'),
    diningClientId: ref('client-id'),
    orderNo: ref(''), orderId: ref(''), orderStatus: ref('pending'),
    successItems: ref([]), successTotal: ref(0), successDiscount: ref(0),
    successMemberValue: ref(null), successPaymentMode: ref(''),
    showCheckoutAuth: ref(false), authorizing: ref(false), authActionStatus: ref('idle'),
    pendingPaymentIntent: ref(null), paying: ref(false), paymentFailed: ref(false),
    paymentConfirming: ref(false), paymentResultUnknown: ref(false),
    payAmount: ref(0), pendingOrderId: ref(''), pendingSubmitRequestId: ref(''),
    myOrders: ref([]), showOrders: ref(false), showCart: ref(true), showSuccess: ref(false),
    successPreserveDraft: ref(false), ordering: ref(false), tableSessionClosed: ref(false),
    paymentMode: ref('pay_later'), reminderRequested: ref(false), earnedCoupon: ref(null),
    cart: ref({ dish_1: 1 }), specCartItems: ref([]), remark: ref(''), selectedCouponId: ref(null),
    totalPrice: ref(20),
    cartItems: ref([{ id: 'dish_1', name: '招牌炒饭', orderName: '招牌炒饭', price: 20, qty: 1 }]),
    finalPrice: ref(20), wechatPayAmount: ref(0), isPrepayMode: ref(false), canSubmitOrder: ref(true),
    orderSuccessTemplateId: ref(''), pickupReminderTemplateId: ref(''),
    showMemberCheckoutChoice: ref(false), memberChoiceJoining: ref(false),
    memberCheckoutBenefitsNeedRefresh: ref(false), isCustomerLoggedIn: ref(false),
  }
  const callbacks = {
    wxLogin: vi.fn(), ensureDiningSession: vi.fn(() => Promise.resolve(true)),
    bindCurrentDiningParticipant: vi.fn(), syncDiningOrders: vi.fn(() => Promise.resolve(true)),
    normalizePaymentMode: vi.fn((mode) => mode || 'pay_later'),
    refreshCustomerAuthState: vi.fn(), saveMyOrders: vi.fn(), startStatusPoll: vi.fn(),
    clearDiningSessionStorage: vi.fn(), refreshAvailableCoupons: vi.fn(() => Promise.resolve()),
  }
  return { state, checkout: useCheckout({ ...state, ...callbacks }) }
}

describe('Demo guest-only checkout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    uni.getStorageSync.mockImplementation((key) => key === 'channel' ? 'DEMO' : '')
    createOrder.mockResolvedValue({ data: { id: 'demo-order', order_no: 'DEMO-1', need_payment: false } })
  })

  it('Demo 顾客点结算直接匿名下单，不展示会员选择层', async () => {
    const { state, checkout } = setup()

    checkout.goCheckout()
    await vi.waitFor(() => expect(createOrder).toHaveBeenCalledTimes(1))

    expect(state.showMemberCheckoutChoice.value).toBe(false)
    expect(joinByEntranceCode).not.toHaveBeenCalled()
  })

  it('正式 TABLE 渠道仍保留会员选择层', () => {
    uni.getStorageSync.mockImplementation((key) => key === 'channel' ? 'TABLE' : '')
    const { state, checkout } = setup()

    checkout.goCheckout()

    expect(state.showMemberCheckoutChoice.value).toBe(true)
    expect(createOrder).not.toHaveBeenCalled()
  })
})
