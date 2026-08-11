import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useTableBillView } from '../useTableBillView.js'

function setup({
  paymentMode = 'table_account',
  diningSessionId = 'sess_1',
  orders = [],
} = {}) {
  return useTableBillView({
    myOrders: ref(orders),
    orderId: ref(''),
    orderStatus: ref('pending'),
    paymentMode: ref(paymentMode),
    diningSessionId: ref(diningSessionId),
    tableSessionTotal: ref(0.02),
    tableSessionClosed: ref(false),
    tableSessionStatus: ref('OPEN'),
    checkoutRequestedAt: ref(''),
    tableCheckouting: ref(false),
    tableSessionClosedAt: ref(''),
    normalizePaymentMode: (m) => m || 'prepay',
    orderItemQty: (item) => Number(item?.qty || 0),
    orderItemCount: (order) => (order?.items || []).reduce((n, i) => n + Number(i.qty || 0), 0),
  })
}

const baseOrder = (overrides = {}) => ({
  id: '100688',
  orderNo: '0688',
  status: 'pending',
  paymentMode: 'table_account',
  diningSessionId: 'sess_1',
  items: [{ name: '测试', qty: 1, price: 0.01 }],
  total: 0.01,
  createdAt: '04:53',
  createdTs: 1,
  pickupNo: '',
  ...overrides,
})

describe('useTableBillView pickup + orderNo display', () => {
  it('pickup_no=8 时 tablePickupNo 为 8', () => {
    const view = setup({ orders: [baseOrder({ pickupNo: '8' })] })
    expect(view.tablePickupNo.value).toBe('8')
  })

  it('pickup_no 为空时 tablePickupNo 为空串（待领取由 UI + enabled 决定）', () => {
    const view = setup({ orders: [baseOrder({ pickupNo: '' })] })
    expect(view.tablePickupNo.value).toBe('')
  })

  it('商家后发/换牌：取会话订单中最新非空 pickupNo', () => {
    const view = setup({
      orders: [
        baseOrder({ id: '1', orderNo: '0688', pickupNo: '8', createdTs: 1 }),
        baseOrder({ id: '2', orderNo: '0691', pickupNo: '12', createdTs: 2 }),
      ],
    })
    expect(view.tablePickupNo.value).toBe('12')
  })

  it('订单批次标题与成功页同一 #尾号 格式', () => {
    const view = setup({
      orders: [
        baseOrder({ id: '100688', orderNo: '0688', createdAt: '04:53', createdTs: 1 }),
        baseOrder({ id: '100691', orderNo: '0691', createdAt: '05:10', createdTs: 2 }),
      ],
    })
    expect(view.tableOrderGroups.value[0].title).toBe('#0688 · 04:53 下单')
    expect(view.tableOrderGroups.value[1].title).toBe('#0691 · 05:10 加菜')
  })

  it('sync 写入 pickupNo 后 tablePickupNo 随之更新', () => {
    const myOrders = ref([baseOrder({ pickupNo: '' })])
    const view = useTableBillView({
      myOrders,
      orderId: ref(''),
      orderStatus: ref('pending'),
      paymentMode: ref('table_account'),
      diningSessionId: ref('sess_1'),
      tableSessionTotal: ref(0.02),
      tableSessionClosed: ref(false),
      tableSessionStatus: ref('OPEN'),
      checkoutRequestedAt: ref(''),
      tableCheckouting: ref(false),
      tableSessionClosedAt: ref(''),
      normalizePaymentMode: (m) => m || 'prepay',
      orderItemQty: (item) => Number(item?.qty || 0),
      orderItemCount: () => 1,
    })
    expect(view.tablePickupNo.value).toBe('')
    myOrders.value = [baseOrder({ pickupNo: '8' })]
    expect(view.tablePickupNo.value).toBe('8')
  })
})
