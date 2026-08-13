import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCheckout } from '../useCheckout.js'
import { createOrder } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

// P0-03 T16/T17/T18: cart-preservation-on-failure and cart->payload semantics.
// These are control/regression tests for already-correct existing behavior
// (not part of the P0-03-01/02/03 fixes) -- they guard against a future
// regression rather than proving a fix.

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

function setup(cartItems) {
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
    cart: ref({ dish_1: 4 }),
    specCartItems: ref([]),
    remark: ref(''),
    selectedCouponId: ref(null),
    totalPrice: ref(100),
    cartItems: ref(cartItems),
    finalPrice: ref(100),
    wechatPayAmount: ref(100),
    isPrepayMode: ref(true),
    canSubmitOrder: ref(true),
    orderSuccessTemplateId: ref('tmpl-order-success'),
    pickupReminderTemplateId: ref('tmpl-pickup'),
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

describe('P0-03 T16: 提交失败不改变 cart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  it('server 拒绝（如售罄/价格已变）时，cart 与 specCartItems 保持提交前原样', async () => {
    const cartItem = { id: 'dish_1', name: '宫保鸡丁', price: 28, qty: 4, orderName: '宫保鸡丁' }
    const { state, checkout } = setup([cartItem])
    createOrder.mockRejectedValue(new Error('菜品已售罄:宫保鸡丁'))

    const cartBefore = JSON.stringify(state.cart.value)
    const specCartBefore = JSON.stringify(state.specCartItems.value)

    const result = await checkout.submitOrder()

    expect(result).toBe(false)
    expect(JSON.stringify(state.cart.value)).toBe(cartBefore)
    expect(JSON.stringify(state.specCartItems.value)).toBe(specCartBefore)
  })
})

describe('P0-03 T17/T18: cart -> payload 字段映射', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  it('T17: 简单商品 qty 正确传递', async () => {
    const simple = { id: 'dish_a', name: 'A', price: 10, qty: 4, orderName: 'A' }
    const { checkout } = setup([simple])
    createOrder.mockResolvedValue({ data: { id: 'order_1', need_payment: false } })

    await checkout.performSubmitOrder()

    expect(createOrder).toHaveBeenCalledWith(
      expect.objectContaining({
        items: [expect.objectContaining({ dish_id: 'dish_a', qty: 4 })],
      }),
      expect.anything(),
    )
  })

  it('T18: spec/addon/remark 商品的语义在 payload 里保持完整', async () => {
    const specItem = {
      id: 'dish_b', name: '水煮牛肉', price: 42, qty: 3,
      orderName: '水煮牛肉(大份、鸡蛋、少辣)',
      specifications: [{ group: '份量', value: '大份' }],
      extras: ['鸡蛋'],
      itemRemark: '少辣',
    }
    const { checkout } = setup([specItem])
    createOrder.mockResolvedValue({ data: { id: 'order_2', need_payment: false } })

    await checkout.performSubmitOrder()

    const sentPayload = createOrder.mock.calls[0][0]
    expect(sentPayload.items).toHaveLength(1)
    const sentItem = sentPayload.items[0]
    expect(sentItem.qty).toBe(3)
    expect(sentItem.specifications).toEqual([{ group: '份量', value: '大份' }])
    expect(sentItem.extras).toEqual(['鸡蛋'])
    // Current legacy-compatible transmission: remark travels folded into
    // `name` (orderName), not as a dedicated field -- see P0-03 audit §22/§8
    // and the explicit instruction not to change this in this phase.
    expect(sentItem.name).toBe('水煮牛肉(大份、鸡蛋、少辣)')
    expect(sentItem.name).toContain('少辣') // REMARK_SEMANTIC_PRESERVED
  })
})
