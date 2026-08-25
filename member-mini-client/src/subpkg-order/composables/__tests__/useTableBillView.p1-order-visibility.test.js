import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ref } from 'vue'
import { useTableBillView } from '../useTableBillView.js'

// P1：桌台账单 vs 现付两种"已点了什么"展示的信息缺口——桌牌号从源头就是
// undefined、每笔子订单没有可报的单号、非分账模式没有本桌合计。

function setup({
  paymentMode = 'table_account',
  orders = [],
} = {}) {
  const myOrders = ref(orders)
  return useTableBillView({
    myOrders,
    orderId: ref(''),
    orderStatus: ref('pending'),
    paymentMode: ref(paymentMode),
    diningSessionId: ref('sess_1'),
    tableSessionTotal: ref(0),
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

describe('useTableBillView tablePickupNo', () => {
  it('从本桌订单里找出带 pickup_no 的那一单，不再永远是 undefined', () => {
    const view = setup({
      paymentMode: 'table_account',
      orders: [
        { id: '1', status: 'preparing', diningSessionId: 'sess_1', paymentMode: 'table_account', items: [], total: 10, createdAt: '12:00', createdTs: 1000, pickupNo: '' },
        { id: '2', status: 'done', diningSessionId: 'sess_1', paymentMode: 'table_account', items: [], total: 10, createdAt: '12:05', createdTs: 2000, pickupNo: '8' },
      ],
    })
    expect(view.tablePickupNo.value).toBe('8')
  })

  it('没有任何一单带 pickup_no 时返回空字符串，不抛错', () => {
    const view = setup({
      paymentMode: 'table_account',
      orders: [
        { id: '1', status: 'preparing', diningSessionId: 'sess_1', paymentMode: 'table_account', items: [], total: 10, createdAt: '12:00', createdTs: 1000 },
      ],
    })
    expect(view.tablePickupNo.value).toBe('')
  })
})

describe('useTableBillView tableOrderGroups orderNo', () => {
  it('每个批次带上可报的订单号，不再只有下单时间', () => {
    const view = setup({
      paymentMode: 'postpay',
      orders: [
        { id: '1001', orderNo: '1001', status: 'preparing', diningSessionId: 'sess_1', paymentMode: 'postpay', items: [], total: 10, createdAt: '12:00', createdTs: 1000 },
      ],
    })
    expect(view.tableOrderGroups.value[0].orderNo).toBe('1001')
  })

  it('订单没有 orderNo 字段时退回 id 后 4 位，不是 undefined', () => {
    const view = setup({
      paymentMode: 'postpay',
      orders: [
        { id: '999888777', status: 'preparing', diningSessionId: 'sess_1', paymentMode: 'postpay', items: [], total: 10, createdAt: '12:00', createdTs: 1000 },
      ],
    })
    expect(view.tableOrderGroups.value[0].orderNo).toBe('8777')
  })
})

describe('useTableBillView orderHistoryTotal / orderHistoryItemCount（prepay 本桌合计）', () => {
  it('把当前订单和历史订单加总，而不是只看最新一笔', () => {
    const view = setup({
      paymentMode: 'prepay',
      orders: [
        { id: '1', status: 'done', diningSessionId: 'sess_1', paymentMode: 'prepay', items: [{ name: '菜A', qty: 1 }], total: 10, createdAt: '12:00', createdTs: 1000 },
        { id: '2', status: 'preparing', diningSessionId: 'sess_1', paymentMode: 'prepay', items: [{ name: '菜B', qty: 2 }], total: 20, createdAt: '12:10', createdTs: 2000 },
      ],
    })
    expect(view.orderHistoryTotal.value).toBe(30)
    expect(view.orderHistoryItemCount.value).toBe(3)
  })

  it('没有任何订单时合计为 0，不抛错', () => {
    const view = setup({ paymentMode: 'prepay', orders: [] })
    expect(view.orderHistoryTotal.value).toBe(0)
    expect(view.orderHistoryItemCount.value).toBe(0)
  })
})

describe('P1 static contract：TableBillSheet.vue 渲染桌牌号和订单号', () => {
  it('声明并渲染 pickupNoEnabled/tablePickupNo，不再是传了没用的 prop', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../../components/TableBillSheet.vue'), 'utf8')
    expect(source).toContain('pickupNoEnabled: { type: Boolean, default: false }')
    expect(source).toContain('tablePickupNo: { type: [String, Number], default: \'\' }')
    expect(source).toContain('v-if="pickupNoEnabled && tablePickupNo"')
    expect(source).toContain('{{ group.orderNo }}')
  })
})

describe('P1 static contract：OrderHistorySheet.vue 渲染本桌合计', () => {
  it('历史订单卡片里有本桌合计小结', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../../components/OrderHistorySheet.vue'), 'utf8')
    expect(source).toContain('history-orders-summary')
    expect(source).toContain('{{ orderHistoryItemCount }}')
    expect(source).toContain('{{ formatPrice(orderHistoryTotal) }}')
  })
})
