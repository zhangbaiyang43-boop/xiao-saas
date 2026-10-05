// Phase 04B: PRINT_FIRST removes the kitchen "accept" click from the normal path, and only there.
// WORKBENCH (the default, and any doubt) keeps every legacy control. Source-contract checks plus a
// behavioural mirror of the table-settle predicate.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8').replace(/\r\n/g, '\n')
const orderManage = read('src/views/OrderManage.vue')
const kitchen = read('src/views/KitchenWorkbench.vue')
const dashboard = read('src/views/Dashboard.vue')
const authStore = read('src/stores/auth.js')

const failures = []
function test(name, fn) {
  try { fn(); console.log(`PASS ${name}`) } catch (error) { failures.push(name); console.error(`FAIL ${name}: ${error.message}`) }
}

test('MODE 1/2/14: auth store defaults to WORKBENCH and only exact PRINT_FIRST switches', () => {
  assert.ok(authStore.includes("const fulfilmentMode = ref('WORKBENCH')"))
  assert.ok(authStore.includes("const isPrintFirst = computed(() => fulfilmentMode.value === 'PRINT_FIRST')"))
  assert.ok(authStore.includes("data.fulfilment_mode === 'PRINT_FIRST' ? 'PRINT_FIRST' : 'WORKBENCH'"))
  assert.ok(authStore.includes("fulfilmentMode.value = 'WORKBENCH'"), 'clearAuth resets to WORKBENCH')
})

test('MODE 6: PRINT_FIRST kitchen workbench hides 开始制作 and the "待接单" framing', () => {
  assert.ok(kitchen.includes("order.status === 'pending' && can('order.accept') && !auth.isPrintFirst"))
  assert.ok(kitchen.includes("auth.isPrintFirst ? '当前订单' : '待制作'"))
  assert.ok(kitchen.includes("label: auth.isPrintFirst ? '当前订单' : formatOrderStatusText('pending')"))
})

test('MODE 13: WORKBENCH controls are still present', () => {
  assert.ok(kitchen.includes('>开始制作</a-button>'))
  assert.ok(kitchen.includes(">完成</a-button>"), 'finish stays for orders already preparing')
  assert.ok(kitchen.includes('补打厨房单'), 'reprint stays')
  assert.ok(orderManage.includes('@click="acceptOrder(order)"'))
  assert.ok(orderManage.includes('@click="acceptTableOrders(selectedTable)"'))
})

test('MODE 6/8: OrderManage hides accept + bulk accept in PRINT_FIRST but keeps reject and reprint', () => {
  const accept = orderManage.split("@click=\"acceptOrder(order)\"").length - 1
  assert.equal(accept, 2)
  assert.equal(orderManage.split("order.status === 'pending' && !isPrintFirst\" type=\"primary\"").length - 1, 2)
  assert.ok(orderManage.includes('selectedTable.pendingOrders.length && !isPrintFirst'))
  assert.ok(orderManage.includes('@click="rejectOrder(order)"'), 'reject remains')
  assert.ok(orderManage.includes('v-if="order.canReject"'))
  assert.ok(orderManage.includes('补打小票'))
})

test('Dashboard / counts: pending is never a to-do in PRINT_FIRST', () => {
  assert.ok(orderManage.includes('const acceptTaskCount = computed(() => (isPrintFirst.value ? 0 : pendingCount.value))'))
  assert.ok(orderManage.includes('acceptTaskCount > 0'))
  assert.ok(orderManage.includes("{ label: '当前订单', value: pendingCount.value"))
  assert.ok(dashboard.includes('orderStats.value.pending > 0 && !auth.isPrintFirst'))
  assert.ok(orderManage.includes("if (isPrintFirst.value && order?.status === 'pending') return '当前订单'"))
})

// ---- behavioural mirror of printFirstSettleable + canSettle ---------------------------------
function makeCanSettle(printFirst) {
  const settleable = (o) => {
    if (!printFirst || o.status !== 'pending') return false
    if (o.paymentStatus === 'paid') return true
    return ['postpay', 'table_account'].includes(o.paymentMode)
  }
  return (t) => Boolean(t.diningSessionId) && t.orders.length > 0
    && t.orders.every((o) => ['done', 'settled'].includes(o.status) || settleable(o))
    && t.orders.some((o) => o.status === 'done' || settleable(o))
    && t.pendingPaymentOrders.length === 0
}
const table = (orders, extra = {}) => ({ diningSessionId: 's1', orders, pendingPaymentOrders: [], ...extra })
const pendingPaid = { status: 'pending', paymentStatus: 'paid', paymentMode: 'prepay' }
const pendingPostpay = { status: 'pending', paymentStatus: 'unpaid', paymentMode: 'postpay' }
const pendingPrepayUnpaid = { status: 'pending', paymentStatus: 'unpaid', paymentMode: 'prepay' }

test('MODE 4/9: WORKBENCH pending still blocks; PRINT_FIRST paid pending does not', () => {
  assert.equal(makeCanSettle(false)(table([pendingPaid])), false)
  assert.equal(makeCanSettle(true)(table([pendingPaid])), true)
  assert.equal(makeCanSettle(true)(table([pendingPaid, { status: 'done' }])), true)
})

test('MODE 10/11: PRINT_FIRST never settles an unpaid prepay order, or a table with a pending_payment order', () => {
  assert.equal(makeCanSettle(true)(table([pendingPrepayUnpaid])), false)
  assert.equal(makeCanSettle(true)(table([pendingPaid], { pendingPaymentOrders: [{}] })), false)
  assert.equal(makeCanSettle(true)(table([pendingPaid, { status: 'preparing' }])), false)
  assert.equal(makeCanSettle(true)(table([pendingPaid, { status: 'refund_pending' }])), false)
  assert.equal(makeCanSettle(true)({ ...table([pendingPaid]), diningSessionId: null }), false)
})

test('MODE 10: postpay unpaid is only offered for settlement behind the 确认收款 dialog', () => {
  assert.equal(makeCanSettle(true)(table([pendingPostpay])), true)
  assert.ok(orderManage.includes('collection_confirmed: true,'))
  assert.ok(orderManage.includes("@click=\"confirmSettle\""))
  assert.ok(orderManage.includes('确认收款'))
})

test('settle uses the same predicate on Dashboard and OrderManage', () => {
  for (const src of [orderManage, dashboard]) {
    assert.ok(src.includes('printFirstSettleable'))
    assert.ok(src.includes("['postpay', 'table_account'].includes("))
  }
})

if (failures.length) {
  console.error(`\n${failures.length} failing: ${failures.join(', ')}`)
  process.exit(1)
}
console.log('\nAll Phase 04B admin checks passed')
