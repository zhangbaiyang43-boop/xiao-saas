import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useTableBillView } from '../useTableBillView.js'

function setup({
  paymentMode = 'table_account',
  tableSessionClosed = false,
  tableSessionStatus = 'OPEN',
  tableSessionClosedAt = '2026-08-08T03:27:00',
  orders = [],
} = {}) {
  const myOrders = ref(orders)
  const view = useTableBillView({
    myOrders,
    orderId: ref(''),
    orderStatus: ref('pending'),
    paymentMode: ref(paymentMode),
    diningSessionId: ref('sess_1'),
    tableSessionTotal: ref(19.9),
    tableSessionClosed: ref(tableSessionClosed),
    tableSessionStatus: ref(tableSessionStatus),
    checkoutRequestedAt: ref(''),
    tableCheckouting: ref(false),
    tableSessionClosedAt: ref(tableSessionClosedAt),
    normalizePaymentMode: (m) => m || 'prepay',
    orderItemQty: (item) => Number(item?.qty || 0),
    orderItemCount: (order) => (order?.items || []).reduce((n, i) => n + Number(i.qty || 0), 0),
  })
  return view
}

describe('useTableBillView settled result', () => {
  it('ACTIVE：可继续加菜，状态不是已结账', () => {
    const view = setup({
      tableSessionClosed: false,
      tableSessionStatus: 'OPEN',
      orders: [{
        id: 'o1',
        status: 'preparing',
        diningSessionId: 'sess_1',
        items: [{ name: '菜', qty: 1, price: 10 }],
        total: 10,
        createdAt: '12:00',
        createdTs: Date.now(),
      }],
    })
    expect(view.isTableSettled.value).toBe(false)
    expect(view.canContinueOrder.value).toBe(true)
    expect(view.tableStatusView.value.title).not.toBe('本桌已结账')
  })

  it('SETTLED：本桌已结账 + 本次用餐已完成，不可继续加菜', () => {
    const view = setup({
      tableSessionClosed: true,
      tableSessionStatus: 'CLOSED',
      orders: [{
        id: 'o1',
        status: 'settled',
        diningSessionId: 'sess_1',
        items: [{ name: '菜', qty: 2, price: 9.95 }],
        total: 19.9,
        createdAt: '12:00',
        createdTs: Date.now(),
      }],
    })
    expect(view.isTableSettled.value).toBe(true)
    expect(view.canContinueOrder.value).toBe(false)
    expect(view.canCheckout.value).toBe(false)
    expect(view.tableStatusView.value.title).toBe('本桌已结账')
    expect(view.tableStatusView.value.desc).toContain('本次用餐已完成')
    expect(view.tableStatusView.value.note).toContain('商家柜台')
  })
})
