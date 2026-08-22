/**
 * P0 — Dashboard.vue actionable-state alignment.
 *
 * Two related production bugs fixed here:
 *
 * 1. Dashboard's own 待结账 count (orderStats.canSettle) was computed by
 *    grouping raw orders by table_no, completely independent of PR #19's
 *    dining_session_id session-isolation contract in OrderManage.vue's
 *    table view. Production evidence: A01 had 31 historical done orders
 *    with dining_session_id=NULL (spanning 2026-06-13..2026-07-10) plus a
 *    separate, unrelated OPEN session (id 7490268597055524864, 4 cancelled
 *    orders) -- the table_no grouping mis-detected 1 settleable table from
 *    the orphans even after PR #19 fixed the table VIEW itself.
 * 2. The settlement todo's raw backend `message` field (e.g. "数据库连接正常")
 *    could leak through to the user-facing todo text whenever the unhealthy
 *    sub-status wasn't specifically printer.
 *
 * No component-render framework exists in this repo (see
 * test-subscription-page-wiring.mjs / test-order-manage-session-isolation.mjs
 * precedent) -- this file combines a literal mirror of the grouping
 * algorithm (run against real fixtures, including the exact production one)
 * with static source-text assertions pinning the guard clauses in both
 * Dashboard.vue and OrderManage.vue.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dashboardSource = fs.readFileSync(path.join(root, 'src/views/Dashboard.vue'), 'utf8')
const orderManageSource = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8')

// ---------------------------------------------------------------------------
// (a) Mirror of Dashboard.vue's loadOrders() canSettle computation. Raw
//     snake_case fields on purpose -- Dashboard consumes getOrders() output
//     directly, it does not go through OrderManage's mapOwnerOrders().
// ---------------------------------------------------------------------------
function computeCanSettle(rawOrders) {
  const sessionMap = {}
  for (const o of rawOrders) {
    if (['cancelled', 'rejected'].includes(o.status)) continue
    if (!o.dining_session_id) continue
    const key = o.dining_session_id
    if (!sessionMap[key]) sessionMap[key] = { orders: [], pendingPaymentOrders: [] }
    if (o.status === 'pending_payment') {
      sessionMap[key].pendingPaymentOrders.push(o)
      continue
    }
    sessionMap[key].orders.push(o)
  }
  return Object.values(sessionMap).filter(t =>
    t.orders.length > 0 &&
    t.orders.every(o => ['done', 'settled'].includes(o.status)) &&
    t.orders.some(o => o.status === 'done') &&
    t.pendingPaymentOrders.length === 0
  ).length
}

function order(partial) {
  return { table_no: 'A01', status: 'done', dining_session_id: null, ...partial }
}

// ---------------------------------------------------------------------------
// Production fixture (2026-08-22 read-only audit, tenant
// 0MBBUYA2qvPhsfVbv0O073QzvU2OsqPl, table A01): 31 sessionless done orders
// (¥536.50) + 11 sessionless settled orders (¥161.00), plus a genuinely
// separate, currently-OPEN DiningSession (id 7490268597055524864) at the
// same table whose 4 orders are all cancelled.
// ---------------------------------------------------------------------------
function productionFixtureOrders() {
  const orphanDone = Array.from({ length: 31 }, (_, i) => order({ id: `orphan-done-${i}`, status: 'done' }))
  const orphanSettled = Array.from({ length: 11 }, (_, i) => order({ id: `orphan-settled-${i}`, status: 'settled' }))
  const openSessionCancelled = Array.from({ length: 4 }, (_, i) =>
    order({ id: `open-session-cancelled-${i}`, status: 'cancelled', dining_session_id: '7490268597055524864' })
  )
  return [...orphanDone, ...orphanSettled, ...openSessionCancelled]
}

// ---- CASE A: exact production fixture -> canSettle=0 ----------------------
{
  const canSettle = computeCanSettle(productionFixtureOrders())
  assert.equal(canSettle, 0, 'the exact production A01 fixture must produce DASHBOARD_CAN_SETTLE=0, not 1')
}

// ---- CASE B: a real single-session done order settles ---------------------
{
  const canSettle = computeCanSettle([order({ id: 's1', dining_session_id: '123', status: 'done' })])
  assert.equal(canSettle, 1, 'a genuine single-session done order must still count as settleable')
}

// ---- done + settled in the same session still counts as 1 -----------------
{
  const canSettle = computeCanSettle([
    order({ id: 's1', dining_session_id: '123', status: 'done' }),
    order({ id: 's2', dining_session_id: '123', status: 'settled' }),
  ])
  assert.equal(canSettle, 1, 'done + settled in the same session must still count as one settleable table')
}

// ---- CASE with pending_payment must block settlement -----------------------
{
  const canSettle = computeCanSettle([
    order({ id: 's1', dining_session_id: '123', status: 'done' }),
    order({ id: 's2', dining_session_id: '123', status: 'pending_payment' }),
  ])
  assert.equal(canSettle, 0, 'a pending_payment order in the session must block settlement, same as OrderManage')
}

// ---- preparing + done in the same session must block settlement -----------
{
  const canSettle = computeCanSettle([
    order({ id: 's1', dining_session_id: '123', status: 'preparing' }),
    order({ id: 's2', dining_session_id: '123', status: 'done' }),
  ])
  assert.equal(canSettle, 0, 'an unfinished (preparing) order in the session must block settlement')
}

// ---- CASE E: same table, two different sessions -> two independent counts -
{
  const canSettle = computeCanSettle([
    order({ id: 's1', table_no: 'A01', dining_session_id: '123', status: 'done' }),
    order({ id: 's2', table_no: 'A01', dining_session_id: '456', status: 'done' }),
  ])
  assert.equal(canSettle, 2, 'same table_no, two different sessions -> two independently settleable tables, never merged into one by table_no')
}

// ---------------------------------------------------------------------------
// (b) Static contract: Dashboard.vue's real source must contain the guard
// clauses the behavioral cases above assume.
// ---------------------------------------------------------------------------
assert.ok(
  dashboardSource.includes('if (!o.dining_session_id) continue'),
  'Dashboard loadOrders must skip orders without dining_session_id before grouping, same as OrderManage',
)
assert.ok(
  !dashboardSource.includes("const t = o.table_no || '-'"),
  'the table_no-only grouping key must be gone from Dashboard.vue',
)
assert.ok(
  dashboardSource.includes('t.pendingPaymentOrders.length === 0'),
  'Dashboard canSettle must also require zero pending_payment orders in the session, matching OrderManage',
)

// ---------------------------------------------------------------------------
// Navigation: the settlement todo must open the table view directly.
// ---------------------------------------------------------------------------
{
  const settleIdx = dashboardSource.indexOf("key: 'settle'")
  assert.ok(settleIdx !== -1, 'settle todo item must exist')
  const actionIdx = dashboardSource.indexOf('action:', settleIdx)
  const nextBraceIdx = dashboardSource.indexOf('})', actionIdx)
  const actionBlock = dashboardSource.slice(actionIdx, nextBraceIdx)
  assert.ok(
    actionBlock.includes("query: { view: 'table' }"),
    'the settlement todo action must navigate with query.view=table, not a bare /orders push',
  )
}

// /orders (no query) -> list; /orders?view=table -> table; anything else -> list
assert.ok(
  orderManageSource.includes("const view = ref(route.query.view === 'table' ? 'table' : 'list')"),
  'OrderManage must default to list, opening table view only for the exact query.view === "table"',
)

// ---------------------------------------------------------------------------
// System status: no raw backend message reaching the user; healthy = silent.
// ---------------------------------------------------------------------------

// Healthy = silent: systemHealthy is a plain every('ok') check, so an all-ok
// status object never reaches the systemStatusUserText branch at all -- proven
// statically since todoItems only pushes the 'system' item when !systemHealthy.
assert.ok(
  dashboardSource.includes('const systemHealthy = computed(() => systemStatusItems.value.every(item => item.status === \'ok\'))'),
  'systemHealthy must remain a strict all-ok check',
)
assert.ok(
  dashboardSource.includes("if (!systemHealthy.value) {"),
  'the system todo item must only ever be pushed when systemHealthy is false',
)

// database must now participate in the health check (previously silently ignored).
assert.ok(
  dashboardSource.includes("{ key: 'database', label: '数据库', status: systemStatus.value.database || 'warning' }"),
  'database must be included in systemStatusItems so a database outage is not silently ignored',
)
// ...but the word must never appear in what a merchant actually reads.
assert.ok(
  !dashboardSource.includes("'数据库'") || dashboardSource.match(/'数据库'/g).length === 1,
  'the literal "数据库" label must only exist once, as the internal systemStatusItems key -- never in user-facing todo text',
)

// The raw backend message must never be used as todo text anymore.
assert.ok(
  !dashboardSource.includes('systemStatus.value.message'),
  'systemStatus.value.message (raw backend diagnostic text) must never be read into user-facing todo text',
)

// Priority-mapped copy, simulating systemStatusUserText's branches directly.
function systemStatusUserText(status) {
  if (status.printer && status.printer !== 'ok') return '打印服务异常，请检查打印机或手动处理订单'
  if (status.payment && status.payment !== 'ok') return '支付服务暂时异常，请稍后重试'
  return '系统服务暂时异常，请稍后重试'
}

// ---- printer bad -----------------------------------------------------------
assert.equal(
  systemStatusUserText({ printer: 'warning', payment: 'ok', message: '数据库连接正常' }),
  '打印服务异常，请检查打印机或手动处理订单',
)

// ---- payment bad -------------------------------------------------------------
assert.equal(
  systemStatusUserText({ printer: 'ok', payment: 'warning', message: '数据库连接正常' }),
  '支付服务暂时异常，请稍后重试',
)

// ---- CASE I (the exact section-18 edge case): printer bad, backend message
// happens to be the healthy-sounding database string -> must show the
// printer copy, never the raw message ------------------------------------
{
  const text = systemStatusUserText({ printer: 'warning', payment: 'ok', message: '数据库连接正常' })
  assert.equal(text, '打印服务异常，请检查打印机或手动处理订单')
  assert.ok(!text.includes('数据库'), 'must never surface the word 数据库 to the merchant')
}

// ---- generic (api/order/database) bad, printer+payment ok -> generic copy --
{
  const text = systemStatusUserText({ printer: 'ok', payment: 'ok', message: '数据库连接正常' })
  assert.equal(text, '系统服务暂时异常，请稍后重试')
  assert.ok(!text.includes('数据库'))
}

// ---- request failure: existing safe copy is preserved, still no raw error --
assert.ok(
  dashboardSource.includes("systemStatusError.value = '系统状态获取失败，请稍后刷新'"),
  'a failed system-status request must keep using a safe, non-technical product copy',
)

console.log('test-dashboard-actionable-state: ok')
