// P0-PAID-PENDING-REJECT: merchant can reject a paid, kitchen-unaccepted order
// from OrderManage. Reject terminates fulfilment only -- it does NOT refund; the
// merchant then uses the existing (Phase 02B certified) refund action.
//
// This locks the Admin side: authority stays 100% backend (order.canReject), the
// second confirmation is honest for a paid order, and no "reject-and-refund"
// orchestration is introduced. Static-source style, same as
// test-p0-refund-merchant-entry.mjs.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8').replace(/\r\n/g, '\n')

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

const rejectFn = slice('function rejectOrder(order) {', '\nasync function finishOrder')

test('A01: reject button is gated ONLY by backend order.canReject, in both render locations', () => {
  const guards = src.match(/v-if="order\.canReject" danger :loading="order\.updating" @click="rejectOrder\(order\)"/g) || []
  assert.equal(guards.length, 2, `reject button must be v-if="order.canReject" in exactly 2 places, found ${guards.length}`)
  // DTO passthrough, no frontend rederivation of the paid+pending rule
  assert.ok(/canReject:\s*o\.can_reject === true/.test(src), 'canReject must be a pure passthrough of o.can_reject')
  assert.ok(!/canReject[^\n]*paymentStatus/.test(src), 'canReject must not be re-derived from paymentStatus in the view')
})

test('A02: cancel ("取消订单") button stays gated by order.canCancel (unpaid only), not opened for paid', () => {
  const cancelGuards = src.match(/v-if="order\.canCancel"[^>]*@click="cancelPendingPaymentOrder\(order\)"/g) || []
  assert.ok(cancelGuards.length >= 1, 'cancel button must remain v-if="order.canCancel"')
  assert.ok(!/canCancel[^\n]*(paid|refund)/i.test(src), 'canCancel must not be widened for paid orders')
})

test('A03: paid reject second confirmation has a paid-specific title', () => {
  assert.ok(/const isPaid = order\.paymentStatus === 'paid'/.test(rejectFn), 'rejectOrder must branch on paid')
  assert.ok(/title:\s*isPaid \? '确认拒绝已付款订单？'/.test(rejectFn), 'paid reject title must say 已付款')
})

test('A04: paid reject confirmation states it does NOT auto-refund', () => {
  assert.ok(/不会自动退款/.test(rejectFn), 'paid reject content must say 不会自动退款')
})

test('A05: paid reject confirmation tells the merchant to complete the refund next', () => {
  assert.ok(/继续点击“退款”/.test(rejectFn), 'paid reject content must guide the merchant to click 退款 next')
  assert.ok(/原路退回顾客/.test(rejectFn), 'paid reject content must state funds return to the customer')
})

test('A06: reject still reconciles/refreshes the order after the request (all branches)', () => {
  assert.ok((rejectFn.match(/await reconcileAfterOrderAction\(\)/g) || []).length >= 2,
    'rejectOrder must reconcile after success and after failure')
  assert.ok(/message\.warning\(isPaid \? '已拒单，请继续点击“退款”完成退款'/.test(rejectFn),
    'paid reject success toast must point to the refund step')
})

test('A07: the existing refund action is untouched (still v-if="order.refundRequired")', () => {
  const refundGuards = src.match(/v-if="order\.refundRequired" danger :loading="order\.refunding" @click="refundPaidOrderClick\(order\)"/g) || []
  assert.equal(refundGuards.length, 2, 'the Phase 02B refund button must still be v-if="order.refundRequired" in 2 places')
})

test('A08: no "拒单并退款" orchestration and no auto-refund call inside rejectOrder', () => {
  assert.ok(!/拒单并退款/.test(src), 'must not add a combined "拒单并退款" button')
  assert.ok(!/refundPaidOrder\s*\(|refundPaidOrderClick\s*\(/.test(rejectFn),
    'rejectOrder must not call any refund function -- reject terminates only, refund is a separate step')
})

console.log(`P0 paid-pending reject: ${failures.length === 0 ? 'passed' : 'FAILED'}`)
if (failures.length > 0) process.exit(1)
