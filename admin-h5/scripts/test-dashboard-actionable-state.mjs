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

// ---- CASE H: pending-order todo is untouched by this phase -----------------
assert.ok(
  dashboardSource.includes("items.push({ key: 'pending', urgent: true, text: `有 ${orderStats.value.pending} 单待接单，请立即处理`, action: () => router.push('/orders') })"),
  'the pending-order todo (text, urgency, navigation) must be unchanged by this phase',
)

// ---------------------------------------------------------------------------
// P0 Dashboard printer-state truth: a CONFIRMED printer problem may produce
// an abnormal todo, while a failed status request may only produce an explicit
// unknown todo. payment/api/order/database status must never independently surface --
// payment=warning in particular reflects CONFIGURATION_NOT_READY (wx_mchid /
// wx_pay_enabled not set up yet), not a RUNTIME_INCIDENT, and belongs on the
// settings/activation page, not the owner's home screen.
// ---------------------------------------------------------------------------

// Mirror of Dashboard.vue's printerActionable + the fixed todo text/gate --
// pure function of the fetched status object, exactly what a real payload
// from getMerchantSystemStatus() would look like.
function computeSystemTodo(status, requestState = 'success') {
  if (requestState === 'error') return '打印机状态暂未确认，请点击重试'
  if (requestState !== 'success') return null
  const printerActionable = Boolean(status.printer) && status.printer !== 'ok'
  if (!printerActionable) return null
  return '打印服务异常，请检查打印机或手动处理订单'
}

assert.equal(computeSystemTodo({ printer: null }, 'loading'), null, 'loading printer state must not be treated as healthy or abnormal')
assert.equal(
  computeSystemTodo({ printer: null }, 'error'),
  '打印机状态暂未确认，请点击重试',
  'failed printer status fetch must render an explicit unknown state',
)

// ---- CASE A: payment=warning, printer=ok -> no system todo at all ---------
assert.equal(
  computeSystemTodo({ api: 'ok', database: 'ok', order: 'ok', payment: 'warning', printer: 'ok', message: '数据库连接正常' }),
  null,
  'payment=warning alone must never produce a home-screen todo (CONFIGURATION_NOT_READY, not a runtime incident)',
)

// ---- CASE B: database=warning, printer=ok -> no technical todo ------------
assert.equal(
  computeSystemTodo({ api: 'ok', database: 'warning', order: 'ok', payment: 'ok', printer: 'ok', message: '数据库连接正常' }),
  null,
  'database=warning alone must never produce a home-screen todo',
)

// ---- CASE C: api=warning, printer=ok -> no technical todo -----------------
assert.equal(
  computeSystemTodo({ api: 'warning', database: 'ok', order: 'ok', payment: 'ok', printer: 'ok' }),
  null,
  'api=warning alone must never produce a home-screen todo',
)

// ---- CASE D: order=warning, printer=ok -> no technical todo ---------------
assert.equal(
  computeSystemTodo({ api: 'ok', database: 'ok', order: 'warning', payment: 'ok', printer: 'ok' }),
  null,
  'order=warning alone must never produce a home-screen todo',
)

// ---- CASE E: printer=warning -> exactly one printer-actionable todo -------
assert.equal(
  computeSystemTodo({ api: 'ok', database: 'ok', order: 'ok', payment: 'ok', printer: 'warning' }),
  '打印服务异常，请检查打印机或手动处理订单',
)

// ---- CASE F: payment=warning + printer=warning -> printer todo only -------
// (there is only ever at most one 'system' todo item -- computeSystemTodo
// returning a single string/null already proves "only printer" structurally,
// this case just pins the combined-failure fixture explicitly.)
assert.equal(
  computeSystemTodo({ api: 'ok', database: 'ok', order: 'ok', payment: 'warning', printer: 'warning', message: '数据库连接正常' }),
  '打印服务异常，请检查打印机或手动处理订单',
)

// ---- CASE G: raw backend message must never be visible, in any fixture ----
for (const status of [
  { api: 'ok', database: 'ok', order: 'ok', payment: 'warning', printer: 'ok', message: '数据库连接正常' },
  { api: 'ok', database: 'ok', order: 'ok', payment: 'ok', printer: 'warning', message: '数据库连接正常' },
  { api: 'warning', database: 'warning', order: 'warning', payment: 'warning', printer: 'ok', message: '数据库连接正常' },
]) {
  const todo = computeSystemTodo(status)
  if (todo) assert.ok(!todo.includes('数据库'), 'the raw backend message must never leak into visible todo text')
}

// ---- CASE (healthy): everything ok, including printer -> no system todo ---
assert.equal(
  computeSystemTodo({ api: 'ok', database: 'ok', order: 'ok', payment: 'ok', printer: 'ok', message: '数据库连接正常' }),
  null,
  'a fully healthy status must never produce a system todo',
)

// ---------------------------------------------------------------------------
// (b) Static contract pinning the real source.
// ---------------------------------------------------------------------------

// The todo gate itself must be printer-only, not the old blanket systemHealthy check.
assert.ok(
  dashboardSource.includes('if (printerActionable.value) {'),
  'the system todo must be gated on printerActionable, not the old blanket !systemHealthy check',
)
assert.ok(
  !dashboardSource.includes('if (!systemHealthy.value)'),
  'the old all-fields-must-be-ok gate must be gone -- payment/api/order/database can no longer trigger the home-screen todo',
)
assert.ok(
  dashboardSource.includes("systemStatusState.value === 'success' &&") &&
    dashboardSource.includes("Boolean(systemStatus.value.printer) && systemStatus.value.printer !== 'ok'"),
  'printerActionable must require a successful status response and a confirmed non-ok printer field',
)
assert.ok(
  dashboardSource.includes("text: '打印服务异常，请检查打印机或手动处理订单'"),
  'the system todo text must be the fixed printer copy, not a structured priority-mapping of multiple fields',
)

// payment/database/api/order copy must be completely gone from the file --
// there is no longer any code path that can produce them.
for (const bannedCopy of ['支付服务暂时异常，请稍后重试', '系统服务暂时异常，请稍后重试', '支付未配置', '支付未启用']) {
  assert.ok(!dashboardSource.includes(bannedCopy), `payment/generic system copy must not exist anywhere in Dashboard.vue: "${bannedCopy}"`)
}

// The raw backend message field must never be read into any user-facing text.
assert.ok(
  !dashboardSource.includes('systemStatus.value.message'),
  'systemStatus.value.message (raw backend diagnostic text) must never be read anywhere in Dashboard.vue',
)

// getMerchantSystemStatus()/loadSystemStatus()/systemStatus itself must be
// retained -- this phase silences the home-screen SURFACE, not the internal
// health fetch (kept for future diagnostics/monitoring per the phase's
// explicit instruction not to delete it).
assert.ok(
  dashboardSource.includes('getMerchantSystemStatus()'),
  'the internal health-check fetch must be retained, not deleted',
)
assert.ok(
  dashboardSource.includes('async function loadSystemStatus()'),
  'loadSystemStatus() must be retained, not deleted',
)
assert.ok(
  dashboardSource.includes("const systemStatus = ref({ api: null, database: null, order: null, payment: null, printer: null"),
  'the systemStatus ref must still carry the full backend payload shape (api/database/order/payment/printer), not just printer',
)
assert.ok(
  dashboardSource.includes("const systemStatusState = ref('loading')"),
  'printer status fetch must start in an explicit loading state',
)
assert.ok(
  dashboardSource.includes("text: '打印机状态暂未确认，请点击重试'"),
  'failed printer status fetch must surface unknown, never abnormal or normal',
)

// Dashboard statistics must reject business-level failures instead of
// presenting the initial numeric zeroes as successfully refreshed facts.
assert.ok(
  dashboardSource.includes("if (r?.code !== 200 || !r.data) throw new Error(r?.msg || 'dashboard stats unavailable')"),
  'dashboard stats non-200 response must enter the existing error state',
)
assert.ok(
  dashboardSource.includes('v-if="!statsError"'),
  'secondary statistics must not render default zero values while the dashboard stats request is failed',
)

// Marketing is tri-state. Missing/failed data cannot default to enabled.
assert.ok(dashboardSource.includes('const marketingError = ref(false)'))
assert.ok(dashboardSource.includes('v-if="marketingError"'))
assert.ok(dashboardSource.includes('营销状态加载失败'))
assert.ok(dashboardSource.includes('marketingEnabled === false'))
assert.ok(dashboardSource.includes('marketingEnabled === true'))
assert.ok(!dashboardSource.includes('consumption_coupon?.enabled !== false'))

// Pre-Candidate-Certification cleanup: the "overall health" aggregation layer
// (systemStatusItems/systemHealthy) had zero consumers after printerActionable
// took over as the sole todo authority -- true dead code, removed rather than
// kept "for future diagnostics" (that reasoning was rejected: it only invites
// someone to wire database/payment/api/order warnings back into the home
// screen later). Pinned here so a regression re-adding either name is caught.
assert.ok(
  !dashboardSource.includes('systemStatusItems'),
  'systemStatusItems must be fully removed -- it was dead code with zero consumers',
)
assert.ok(
  !dashboardSource.includes('systemHealthy'),
  'systemHealthy must be fully removed -- it was dead code with zero consumers',
)
// The 数据库/系统服务/订单服务/支付服务 UI labels only ever existed as quoted
// object-literal values inside systemStatusItems -- with that gone, those
// exact quoted forms must be gone too. Checking the quoted form (not a bare
// substring match) deliberately allows the word to still appear in an
// explanatory code comment (it does, once, describing why the raw message
// field is never read) without that being mistaken for a UI label.
for (const removedLabel of ["label: '数据库'", "label: '系统服务'", "label: '订单服务'", "label: '支付服务'"]) {
  assert.ok(!dashboardSource.includes(removedLabel), `label from the removed systemStatusItems array must not remain: "${removedLabel}"`)
}

console.log('test-dashboard-actionable-state: ok')
