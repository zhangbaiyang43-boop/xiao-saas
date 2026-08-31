// P0-REFUND-MERCHANT-ENTRY (Phase 02B): merchant refund entry in OrderManage.
//
// Backend refund truth layer is frozen and certified (P0-REFUND-BACKEND-02A,
// candidate 980af8b). This suite locks the Admin side of the contract so a later
// edit to OrderManage.vue cannot silently regress it:
//
//   - the refund action is gated ONLY by the server flag order.refundRequired
//     (backend refund_required), never by a frontend-rebuilt state machine;
//   - refund_status success / processing / failed each render a distinct,
//     truthful line and tag;
//   - clicking refund always goes through a second confirmation showing a
//     read-only refund amount (no amount input; P0 is full-refund only);
//   - the submit path is double-click protected, distinguishes processing from
//     success in its toast, and re-syncs the order from the backend afterwards;
//   - order.status vocabulary is untouched (refund is a payment-dimension fact).
//
// Same static-source style as scripts/test-order-manage-just-served.mjs.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8').replace(/\r\n/g, '\n')

const failures = []
function test(name, fn) {
  try {
    fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}

function slice(startMarker, endMarker) {
  const rest = src.split(startMarker, 2)[1]
  if (rest == null) throw new Error(`marker not found: ${startMarker}`)
  const end = rest.indexOf(endMarker)
  if (end === -1) throw new Error(`end marker not found: ${endMarker}`)
  return rest.slice(0, end)
}

const refundClickFn = slice('function refundPaidOrderClick(order) {', '\nasync function reprintOrderTicket')
const refundLineFn = slice('function refundLine(order) {', '\n// 退款金额只读展示')
const mapOwnerFn = slice('function mapOwnerOrders(raw) {', '\nfunction readOwnerCursor')

// The two render locations that carry the refund button: the table-detail row
// and the flat list card. Both must behave identically.
const refundButtonGuards = src.match(/v-if="order\.refundRequired"[^>]*@click="refundPaidOrderClick\(order\)"/g) || []

test('DTO: mapOwnerOrders consumes the backend refund fields verbatim', () => {
  assert.ok(/refundRequired:\s*o\.refund_required === true/.test(mapOwnerFn), 'refundRequired must map o.refund_required')
  assert.ok(/refundStatus:\s*o\.refund_status/.test(mapOwnerFn), 'refundStatus must map o.refund_status')
  assert.ok(/refundAmount:\s*o\.refund_amount/.test(mapOwnerFn), 'refundAmount must map o.refund_amount')
  assert.ok(/refundedAt:\s*o\.refunded_at/.test(mapOwnerFn), 'refundedAt must map o.refunded_at')
})

test('AUTHORITY: refund action is gated only by order.refundRequired, not a frontend rederivation', () => {
  assert.equal(refundButtonGuards.length, 2, `refund button must appear in exactly the 2 render locations, found ${refundButtonGuards.length}`)
  // each refund button's v-if is exactly order.refundRequired -- no ORed alternative
  const exactGuards = src.match(/<a-button v-if="order\.refundRequired" danger :loading="order\.refunding" @click="refundPaidOrderClick\(order\)"/g) || []
  assert.equal(exactGuards.length, 2, 'both refund buttons must be guarded by exactly v-if="order.refundRequired"')
  // no frontend copy of the backend "paid AND status in (cancelled, rejected)" rule
  assert.ok(!/\[['"]cancelled['"],\s*['"]rejected['"]\]\.includes\(\s*order\.status\s*\)/.test(src), 'must not re-derive terminal-state authority in the view')
  assert.ok(!/paymentStatus === ['"]paid['"][^\n]*(cancelled|rejected)/.test(src), 'must not re-derive paid+terminal authority in the view')
  assert.ok(!/(cancelled|rejected)[^\n]*paymentStatus === ['"]paid['"]/.test(src), 'must not re-derive paid+terminal authority in the view')
})

test('UI_CONTRACT_01: refund_required=true -> refund action visible in both render locations', () => {
  assert.equal(refundButtonGuards.length, 2)
})

test('UI_CONTRACT_02: refund_required=false -> refund action hidden (no other trigger path)', () => {
  const triggers = src.match(/@click="refundPaidOrderClick\(order\)"/g) || []
  assert.equal(triggers.length, 2, 'refundPaidOrderClick must only be reachable from the 2 guarded buttons')
  for (const g of refundButtonGuards) {
    assert.ok(g.startsWith('v-if="order.refundRequired"'), `refund button guard must be exactly order.refundRequired: ${g}`)
  }
})

test('UI_CONTRACT_03: refund_status=processing -> "退款处理中" line + tag, and NOT gated as an action', () => {
  assert.ok(/status === 'processing'/.test(refundLineFn), 'refundLine must branch on processing')
  assert.ok(/退款处理中/.test(refundLineFn), 'processing branch must say 退款处理中')
  assert.ok((src.match(/order\.refundStatus === 'processing'[^>]*>\s*退款处理中/g) || []).length >= 2, 'a 退款处理中 tag must render in both locations')
  // backend already sets refund_required=false for processing; the button must
  // not be independently re-enabled on refundStatus
  assert.ok(!/refundStatus[^\n]*(!==|===)\s*'processing'[^\n]*v-if/.test(src), 'button visibility must not depend on refundStatus')
})

test('UI_CONTRACT_04: refund_status=success -> "已退款" line with amount + tag, no button', () => {
  assert.ok(/status === 'success'/.test(refundLineFn), 'refundLine must branch on success')
  assert.ok(/已退款 ¥\$\{amount\.toFixed\(2\)\}/.test(refundLineFn), 'success line must render 已退款 with a ¥ amount')
  assert.ok((src.match(/order\.refundStatus === 'success'[^>]*>\s*已退款/g) || []).length >= 2, 'a 已退款 tag must render in both locations')
})

test('UI_CONTRACT_05: refund_status=failed + refund_required=true -> "退款失败" line + "重新退款" button', () => {
  assert.ok(/status === 'failed'/.test(refundLineFn), 'refundLine must handle failed')
  assert.ok(/退款失败/.test(refundLineFn), 'failed branch must say 退款失败')
  const relabels = src.match(/order\.refundStatus === 'failed' \? '重新退款' : '退款'/g) || []
  assert.equal(relabels.length, 2, `both refund buttons must relabel to 重新退款 on failed, found ${relabels.length}`)
})

test('UI_CONTRACT_06: clicking refund opens a second confirmation', () => {
  assert.ok(/Modal\.confirm\(\{/.test(refundClickFn), 'refundPaidOrderClick must use Modal.confirm')
  assert.ok(/title:\s*'确认退款？'/.test(refundClickFn), 'confirm title must be 确认退款？')
  assert.ok(/okText:\s*'确认退款'/.test(refundClickFn), 'confirm OK must be 确认退款')
})

test('UI_CONTRACT_07: confirmation shows a read-only refund amount (no amount input, full refund only)', () => {
  assert.ok(/实付金额 ¥\$\{paid\.toFixed\(2\)\}/.test(refundClickFn), 'confirm must show 实付金额')
  assert.ok(/退款金额 ¥\$\{refundAmount\.toFixed\(2\)\}/.test(refundClickFn), 'confirm must show 退款金额')
  assert.ok(/原路退回顾客/.test(refundClickFn), 'confirm must state funds return to the customer')
  assert.ok(!/a-input|a-input-number|<input/i.test(refundClickFn), 'confirm must not contain an amount input')
  // amount source: backend-confirmed refund_amount on success, else the order's paid total
  assert.ok(/order\.refundStatus === 'success' && order\.refundAmount != null\) return order\.refundAmount/.test(src), 'refundDisplayAmount must prefer backend refund_amount on success')
  assert.ok(/return Number\(order\.total \|\| 0\)/.test(src), 'refundDisplayAmount must fall back to order.total (backend-validated paid amount)')
})

test('UI_CONTRACT_08: submit path is double-click protected', () => {
  assert.ok(/if \(order\.refunding\) return/.test(refundClickFn), 'must early-return while a refund is in flight')
  assert.ok(refundClickFn.indexOf('order.refunding = true') < refundClickFn.indexOf('await refundPaidOrder(order.id)'), 'order.refunding must be set before the request')
  assert.ok((src.match(/:loading="order\.refunding"/g) || []).length >= 2, 'both refund buttons must bind :loading to order.refunding')
})

test('UI_CONTRACT_09: API processing result must not show "退款成功"', () => {
  assert.ok(/res\.data && res\.data\.refund_status === 'processing'/.test(refundClickFn), 'onOk must inspect res.data.refund_status')
  assert.ok(/message\.info\('退款申请已提交，正在处理中'\)/.test(refundClickFn), 'processing must show an info toast')
  const successIdx = refundClickFn.indexOf("message.success('退款成功')")
  const elseIdx = refundClickFn.indexOf('} else {')
  assert.ok(successIdx > elseIdx && elseIdx !== -1, '退款成功 toast must be in the non-processing else branch only')
})

test('UI_CONTRACT_10: after any refund outcome the order is re-synced from the backend', () => {
  const finallyBlock = refundClickFn.slice(refundClickFn.indexOf('} finally {'))
  assert.ok(/await reconcileAfterOrderAction\(\)/.test(finallyBlock), 'finally must await reconcileAfterOrderAction() (syncNow) for success/processing/failed alike')
  assert.ok(/async function reconcileAfterOrderAction\(\)\s*\{\s*await syncNow\(\)/.test(src), 'reconcileAfterOrderAction must delegate to syncNow()')
})

test('ERRORS: 400/409/502 business messages are surfaced, 403 is left to the interceptor', () => {
  assert.ok(/message\.error\(\(res && res\.msg\) \|\| '当前订单无法退款，请刷新后重试'\)/.test(refundClickFn), 'non-200 body must prefer the backend msg with a safe fallback')
  assert.ok(/err\?\.response\?\.status !== 403/.test(refundClickFn), '403 must be skipped (request interceptor already warns)')
})

test('SCOPE: order.status vocabulary is untouched (refund is a payment-dimension fact)', () => {
  assert.ok(!/tag-refunded|tag-refund_processing/.test(src), 'must not add refund states to the order.status tag vocabulary')
  assert.ok(!/order\.status === 'refunded'|order\.status === 'refund_processing'/.test(src), 'must not invent order.status refund values')
})

test('SCOPE: API client is not touched from here (refundPaidOrder already exists in src/api)', () => {
  assert.ok(/import \{[^}]*refundPaidOrder[^}]*\} from '\.\.\/api'/.test(src), 'refundPaidOrder must be imported from the existing api module')
})

console.log(`P0-refund merchant entry: ${failures.length === 0 ? 'passed' : 'FAILED'}`)
if (failures.length > 0) process.exit(1)
