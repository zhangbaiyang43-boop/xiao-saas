// P0-REFUND-PROCESSING-RECONCILIATION (Admin side).
//
// A refund that the provider returns as PROCESSING never converges on its own
// (no WeChat refund callback; GET /orders is a pure DB read). OrderManage now does
// a BOUNDED poll of the QUERY-ONLY reconcile endpoint while a row is "processing".
// This locks: it uses the new endpoint (never the refund command), it is capped at
// 3 attempts with one in-flight per order, it also fires for a pre-existing
// processing row loaded from GET /orders (the ¥0.02 canary case), and it clears its
// timers on unmount. Static-source style, same as test-p0-refund-merchant-entry.mjs.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8').replace(/\r\n/g, '\n')
const api = fs.readFileSync(path.join(root, 'src/api/index.js'), 'utf8').replace(/\r\n/g, '\n')

const failures = []
function test(name, fn) {
  try { fn(); console.log(`PASS ${name}`) }
  catch (error) { failures.push({ name, error }); console.error(`FAIL ${name}: ${error.message}`) }
}
function slice(startMarker, endMarker) {
  const rest = src.split(startMarker, 2)[1]
  if (rest == null) throw new Error(`marker not found: ${startMarker}`)
  const end = rest.indexOf(endMarker)
  if (end === -1) throw new Error(`end marker not found: ${endMarker}`)
  return rest.slice(0, end)
}

// the whole reconcile-polling block lives between refundPaidOrderClick and reprintOrderTicket
const pollBlock = slice('function refundPaidOrderClick(order) {', '\nasync function reprintOrderTicket')

test('API: a dedicated query-only reconcile client exists and is separate from the refund command', () => {
  assert.ok(/export const reconcileRefundStatus = \(id\) => request\.post\(`\/v1\/orders\/\$\{id\}\/refund\/reconcile`\)/.test(api),
    'reconcileRefundStatus must POST /v1/orders/{id}/refund/reconcile')
  assert.ok(/export const refundPaidOrder = \(id\) => request\.post\(`\/v1\/orders\/\$\{id\}\/refund`\)/.test(api),
    'the refund command client must stay unchanged')
  assert.ok(/import \{[^}]*reconcileRefundStatus[^}]*\} from '\.\.\/api'/.test(src),
    'OrderManage must import reconcileRefundStatus')
})

test('A01: a refund API result of processing schedules the reconcile poll', () => {
  assert.ok(/res\.data\.refund_status === 'processing'\)\s*\{\s*message\.info\('退款申请已提交，正在处理中'\)\s*startRefundReconcile\(order\.id\)/.test(pollBlock),
    'the processing branch of refundPaidOrderClick must call startRefundReconcile(order.id)')
})

test('A02: a pre-existing processing order (from GET /orders) also schedules the reconcile poll', () => {
  assert.ok(/watch\(\s*\(\) => orders\.value\.filter\(\(o\) => o\.refundStatus === 'processing'\)/.test(src),
    'a watch over processing orders must exist')
  assert.ok(/startRefundReconcile\(id\)/.test(src), 'the watch must start reconcile for each processing order id')
  assert.ok(/\{ immediate: true \}/.test(pollBlock), 'the watch must run immediately so a page (re)load converges the canary')
})

test('A03: only processing orders are reconciled', () => {
  assert.ok(/o\.refundStatus === 'processing'/.test(pollBlock), 'the trigger filters on refundStatus === processing')
  assert.ok(/order\.refundStatus !== 'processing'\)\s*\{[\s\S]{0,80}refundReconcileSettled\.add\(id\)/.test(pollBlock),
    'runRefundReconcile must bail out (settle) if the order is no longer processing')
})

test('A04: a success result stops the poll and re-syncs the row', () => {
  assert.ok(/rs === 'success' \|\| rs === 'failed'\)\s*\{\s*refundReconcileSettled\.add\(id\)\s*await reconcileAfterOrderAction\(\)/.test(pollBlock),
    'success/failed must settle the order and reconcileAfterOrderAction()')
})

test('A05: a failed result stops the poll', () => {
  // covered by the same success/failed branch above
  assert.ok(/rs === 'success' \|\| rs === 'failed'/.test(pollBlock), 'failed shares the terminal branch with success')
})

test('A06: processing is bounded to a fixed max number of attempts', () => {
  assert.ok(/const REFUND_RECONCILE_DELAYS = \[2000, 5000, 10000\]/.test(pollBlock), 'exactly 3 bounded delays')
  assert.ok(/attempt >= REFUND_RECONCILE_DELAYS\.length\)\s*\{[\s\S]{0,120}refundReconcileSettled\.add\(id\)\s*return/.test(pollBlock),
    'once the delays are exhausted the poll must stop (settle), not loop forever')
  assert.ok(!/setInterval\(/.test(pollBlock), 'must not use setInterval')
})

test('A07: an inconclusive / errored reconcile is treated as processing and retried within the same cap', () => {
  assert.ok(/catch \{\s*rs = null/.test(pollBlock), 'a thrown/errored reconcile maps to null (inconclusive)')
  assert.ok(/scheduleRefundReconcileAttempt\(id, attempt \+ 1\)/.test(pollBlock),
    'inconclusive/processing schedules the next bounded attempt')
})

test('A08: at most one in-flight reconcile request per order', () => {
  assert.ok(/const refundReconcileInflight = new Set\(\)/.test(pollBlock), 'per-order in-flight guard')
  assert.ok(/if \(refundReconcileSettled\.has\(id\) \|\| refundReconcileInflight\.has\(id\)\) return/.test(pollBlock),
    'runRefundReconcile must skip if one is already in flight')
  assert.ok(/refundReconcileInflight\.add\(id\)/.test(pollBlock), 'the in-flight flag is set before the request')
  assert.ok(/refundReconcileInflight\.delete\(id\)/.test(pollBlock), 'the in-flight flag is cleared (finally)')
  assert.ok(/refundReconcileTimers\.has\(id\) \|\| refundReconcileInflight\.has\(id\)\) return/.test(pollBlock),
    'startRefundReconcile must not stack a second timer/request for the same order')
})

test('A09: component unmount clears all pending reconcile timers', () => {
  assert.ok(/function stopAllRefundReconcile\(\)\s*\{[\s\S]{0,160}clearTimeout\(timer\)[\s\S]{0,60}refundReconcileTimers\.clear\(\)/.test(pollBlock),
    'stopAllRefundReconcile clears every timer')
  assert.ok(/onUnmounted\(stopAllRefundReconcile\)/.test(pollBlock), 'it is wired to onUnmounted')
  assert.ok(/import \{[^}]*onUnmounted[^}]*\} from 'vue'/.test(src), 'onUnmounted is imported')
})

test('A10: the poll calls the new reconcile endpoint', () => {
  assert.ok(/const res = await reconcileRefundStatus\(id\)/.test(pollBlock), 'runRefundReconcile calls reconcileRefundStatus')
})

test('A11: the poll NEVER calls the original refund command', () => {
  const runFn = pollBlock.slice(pollBlock.indexOf('async function runRefundReconcile'))
  assert.ok(!/refundPaidOrder\s*\(/.test(runFn), 'runRefundReconcile must not call refundPaidOrder')
  assert.ok(!/refundPaidOrderClick\s*\(/.test(runFn), 'runRefundReconcile must not re-open the refund dialog')
})

test('A12: on success the row is refreshed from the backend (existing 已退款 ¥X.XX rendering, unchanged)', () => {
  assert.ok(/已退款 ¥\$\{amount\.toFixed\(2\)\}/.test(src), 'the success line rendering from Phase 02B is untouched')
  assert.ok(/await reconcileAfterOrderAction\(\)/.test(pollBlock) && /async function reconcileAfterOrderAction\(\)\s*\{\s*await syncNow\(\)/.test(src),
    'success path reconciles via the existing syncNow path')
})

test('A13: exhausted processing leaves the existing "退款处理中" copy in place (no fake state)', () => {
  assert.ok(/退款处理中，请稍后刷新查看结果/.test(src), 'the processing line copy is unchanged')
  const runFn = pollBlock.slice(pollBlock.indexOf('async function runRefundReconcile'))
  assert.ok(!/\border\.refundStatus\s*=[^=]/.test(runFn), 'the poll must never locally assign order.refundStatus')
  assert.ok(!/message\.success\(/.test(runFn) && !/message\.error\(/.test(runFn),
    'the poll is silent -- it re-syncs from the backend, it does not toast its own verdict')
})

test('A14: no "再次退款 while processing" behaviour and order.status vocabulary untouched', () => {
  assert.ok(!/tag-refunded|tag-refund_processing/.test(src), 'no new order.status refund tags')
  // the refund button is still hidden while processing (Phase 02B: refund_required=false)
  assert.ok(/v-if="order\.refundRequired"[^>]*@click="refundPaidOrderClick\(order\)"/.test(src),
    'the refund button stays gated by order.refundRequired')
})

console.log(`P0 refund processing reconcile: ${failures.length === 0 ? 'passed' : 'FAILED'}`)
if (failures.length > 0) process.exit(1)
