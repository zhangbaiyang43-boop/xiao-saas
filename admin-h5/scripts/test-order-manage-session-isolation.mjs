/**
 * P0 — OrderManage.vue table-view session isolation.
 *
 * Production incident: 商家后台 桌台视图 aggregated 31 historical done orders
 * with dining_session_id=NULL under table A01 into one "可结账" card (¥536.50),
 * because tableGroups' fallback `table:${tableNo}` grouping key and canSettle
 * had no session requirement at all. Clicking 结账 -> 确认收款 then failed with
 * the backend's (correct, deliberate) "请指定要结账的会话" once it discovered a
 * genuinely separate OPEN DiningSession also existed at that table.
 *
 * No component-render framework exists in this repo (see
 * test-subscription-page-wiring.mjs precedent) -- this file combines:
 *   (a) a literal mirror of tableGroups'/canSettle's grouping algorithm,
 *       run against the exact production fixture, to prove the *behavior*
 *       real orders would see, and
 *   (b) static source-text assertions pinning the exact guard clauses in
 *       OrderManage.vue, so a future edit that silently drops one of them
 *       (even while leaving the mirrored algorithm here untouched) still
 *       fails this test.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8')

// ---------------------------------------------------------------------------
// (a) Mirror of OrderManage.vue's tableGroups computed (grouping + canSettle
//     only -- pendingOrders/preparingOrders/isSettled omitted, not needed here).
// ---------------------------------------------------------------------------
function buildTableGroups(orders) {
  const map = {}
  for (const o of orders) {
    if (['cancelled', 'rejected'].includes(o.status)) continue
    if (!o.diningSessionId) continue
    const key = `session:${o.diningSessionId}`
    if (!map[key]) map[key] = { groupKey: key, tableNo: o.table, diningSessionId: o.diningSessionId, orders: [], pendingPaymentOrders: [], total: 0 }
    if (o.status === 'pending_payment') {
      map[key].pendingPaymentOrders.push(o)
      continue
    }
    map[key].orders.push(o)
    map[key].total += o.total
  }
  return Object.values(map).map(t => ({
    ...t,
    canSettle: Boolean(t.diningSessionId) && t.orders.length > 0 && t.orders.every(o => ['done', 'settled'].includes(o.status)) && t.orders.some(o => o.status === 'done') && t.pendingPaymentOrders.length === 0,
  }))
}

function order(partial) {
  return { table: 'A01', total: 0, status: 'done', diningSessionId: null, ...partial }
}

// ---------------------------------------------------------------------------
// Production fixture (2026-08-22 read-only audit against tenant
// 0MBBUYA2qvPhsfVbv0O073QzvU2OsqPl, table A01): 31 sessionless done orders
// (¥536.50) + 11 sessionless settled orders (¥161.00), all dining_session_id
// NULL, spanning 2026-06-13..2026-07-10 -- plus a genuinely separate,
// currently-OPEN DiningSession (id 7490268597055524864) at the same table
// whose 4 orders are all cancelled (so they never even reach buildTableGroups,
// which already skips cancelled/rejected -- included here for completeness).
// ---------------------------------------------------------------------------
function productionFixtureOrders() {
  const orphanDone = Array.from({ length: 31 }, (_, i) => order({ id: `orphan-done-${i}`, status: 'done', total: 536.50 / 31 }))
  const orphanSettled = Array.from({ length: 11 }, (_, i) => order({ id: `orphan-settled-${i}`, status: 'settled', total: 161.00 / 11 }))
  const openSessionCancelled = Array.from({ length: 4 }, (_, i) =>
    order({ id: `open-session-cancelled-${i}`, status: 'cancelled', diningSessionId: '7490268597055524864', total: 95 / 4 })
  )
  return [...orphanDone, ...orphanSettled, ...openSessionCancelled]
}

// ---- CASE 1/2: 31 sessionless done orders never form a settleable group ----
{
  const groups = buildTableGroups(productionFixtureOrders())
  // The OPEN session's orders are all cancelled -> buildTableGroups skips them
  // entirely -> no group is produced for that session at all, and definitely
  // no group at all keyed purely by table_no.
  assert.equal(groups.length, 0, 'the exact production A01 fixture must produce zero table groups')
  assert.ok(!groups.some(g => g.groupKey === 'table:A01'), 'no table-number-only fallback group may ever exist')
  assert.ok(!groups.some(g => g.canSettle), 'nothing in the production fixture may show canSettle=true')
}

// ---- CASE 3: a real session-backed group can still settle -----------------
{
  const groups = buildTableGroups([
    order({ id: 's1', diningSessionId: '123', status: 'done', total: 30 }),
  ])
  assert.equal(groups.length, 1)
  assert.equal(groups[0].canSettle, true, 'a genuine single-session done order must still be settleable')
}

// ---- CASE 4: two sessions at the same table stay separate groups ----------
{
  const groups = buildTableGroups([
    order({ id: 'a1', diningSessionId: '123', status: 'settled', total: 20 }),
    order({ id: 'b1', diningSessionId: '456', status: 'done', total: 40 }),
  ])
  assert.equal(groups.length, 2, 'same table_no, two different sessions -> two groups, never merged')
  const keys = groups.map(g => g.groupKey).sort()
  assert.deepEqual(keys, ['session:123', 'session:456'])
}

// ---- Legacy hint must not nag forever over already-settled orphans --------
// (11 of the 42 production orphans are already settled -- nothing left to
// action on those; the hint exists to point at orders that still need
// attention, not to permanently flag fully-resolved history.)
function hasSessionlessActiveOrders(orders) {
  return orders.some(o => !o.diningSessionId && !['cancelled', 'rejected', 'settled'].includes(o.status))
}
{
  const onlySettledOrphans = Array.from({ length: 11 }, (_, i) => order({ id: `settled-only-${i}`, status: 'settled' }))
  assert.equal(hasSessionlessActiveOrders(onlySettledOrphans), false, 'a tenant with only settled sessionless orders must not see a persistent legacy-orders hint')
  assert.equal(hasSessionlessActiveOrders(productionFixtureOrders()), true, 'the production fixture still has actionable (done) orphans and must show the hint')
}
assert.ok(
  source.includes("!['cancelled', 'rejected', 'settled'].includes(o.status)"),
  'hasSessionlessActiveOrders must exclude settled orders, not just cancelled/rejected',
)

// ---- CASE 5: sessionless orders are not dropped from the underlying data --
// (buildTableGroups only governs the table VIEW; the real component's order
// list (sortedOrders/visibleOrders) reads directly from orders.value, which
// this fix never touches -- verified statically below.)
{
  assert.ok(
    !/sortedOrders = computed\(\(\) => \{\s*let list = statusFilter\.value\s*\? orders\.value\.filter\(o => o\.status === statusFilter\.value\)\s*: orders\.value\.filter\(o => o\.status !== 'pending_payment' && o\.diningSessionId\)/.test(source),
    'the order list must not gain a diningSessionId filter -- sessionless orders must remain visible there',
  )
  assert.ok(source.includes("orders.value.filter(o => o.status !== 'pending_payment')"), 'order list base filter must remain status-only, unfiltered by session')
}

// ---------------------------------------------------------------------------
// (b) Static contract: the real component source must actually contain the
// guard clauses the behavioral cases above assume.
// ---------------------------------------------------------------------------

// ---- CASE 2 (static): grouping loop must skip sessionless orders entirely --
assert.ok(
  source.includes('if (!o.diningSessionId) continue'),
  'tableGroups must skip orders without a diningSessionId before ever building a group',
)
assert.ok(
  !source.includes('table:${o.table}'),
  'the table-number-only fallback grouping key must be gone',
)

// ---- CASE 3/6 (static): canSettle must require a session, independent of grouping --
assert.ok(
  source.includes('canSettle: Boolean(t.diningSessionId) &&'),
  'canSettle must explicitly require diningSessionId as its own fail-closed guard, not rely solely on the grouping loop',
)

// ---- CASE 6 (static): settleTableClick must fail closed before opening the dialog --
{
  const fnIdx = source.indexOf('function settleTableClick(table) {')
  assert.ok(fnIdx !== -1, 'settleTableClick must exist')
  const dialogIdx = source.indexOf('showSettleDialog.value = true', fnIdx)
  const guardIdx = source.indexOf('if (!table?.diningSessionId)', fnIdx)
  assert.ok(guardIdx !== -1 && guardIdx < dialogIdx, 'settleTableClick must reject a session-less table before opening the confirm-payment dialog')
  const guardBlock = source.slice(guardIdx, dialogIdx)
  assert.ok(guardBlock.includes('return'), 'the session-less guard must return before reaching showSettleDialog.value = true')
}

// ---- CASE 7 (static): the settle API contract itself is untouched ---------
assert.ok(
  source.includes('await settleTable(settlingTable.value.tableNo, settlingTable.value.diningSessionId)'),
  'confirmSettle must keep calling settleTable(tableNo, diningSessionId) unchanged',
)

// ---- 待结账 stat must not count sessionless done orders --------------------
assert.ok(
  source.includes("orders.value.filter(o => o.status === 'done' && o.diningSessionId).length"),
  'doneCount (待结账 stat) must require diningSessionId, matching the production fixture (31 sessionless done orders must not inflate this number)',
)
{
  const fixture = productionFixtureOrders()
  const doneCount = fixture.filter(o => o.status === 'done' && o.diningSessionId).length
  assert.equal(doneCount, 0, 'with the exact production fixture, 待结账 must read 0, not 31')
}

console.log('test-order-manage-session-isolation: ok')
