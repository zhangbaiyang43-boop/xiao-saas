// Phase-05A acceptance suite: OrderManage new-order discovery + reject-order safety.
//
// No Vue render framework exists in this repo (see test-dashboard-actionable-state.mjs
// precedent), so this combines static source assertions on the real file with a
// structural check that business logic actually lives inside the confirm dialog's
// onOk callback (not just that "Modal.confirm" appears somewhere in the file).
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execSync } from 'node:child_process'

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
  return endMarker ? rest.split(endMarker, 1)[0] : rest
}

// ---------------------------------------------------------------------------
// F1: new-order discovery via the existing isHighlighted authority.
// ---------------------------------------------------------------------------

test('1. OrderManage adopts the existing isHighlighted authority from useWorkbenchSync', () => {
  const destructure = slice('const {', '} = useWorkbenchSync({')
  assert.ok(/^\s*isHighlighted,\s*$/m.test(destructure), 'isHighlighted must be destructured from the same useWorkbenchSync() call OrderManage already uses -- not a new composable instance, not a new import path')
})

test('2. New-order visual state is driven by isHighlighted(order.id), not a second highlight system', () => {
  // Must call the real function against the real per-order id, in all three
  // surfaces a merchant can be looking at: the list-view card, the table-view
  // grid tile, and the table-detail drawer's per-order row.
  const callSites = [...src.matchAll(/isHighlighted\(order\.id\)/g)]
  assert.ok(callSites.length >= 3, `expected isHighlighted(order.id) to drive at least 3 template surfaces (list card, drawer row, badge), found ${callSites.length}`)
  assert.ok(src.includes("'table-tile--new': table.orders.some((o) => isHighlighted(o.id))"), 'the table grid tile must flag itself as new by checking its own orders through the same isHighlighted authority, not a separately tracked id set')

  // MUST NOT: a parallel, hand-rolled highlight state (the whole point is reuse).
  assert.ok(!/const\s+newOrderIds/.test(src), 'must not introduce a parallel newOrderIds ref/state')
  assert.ok(!src.includes('localStorage') || !slice('function rejectOrder', 'async function finishOrder').includes('localStorage'), 'no localStorage-backed highlight state near the touched code')
  assert.ok(!/setTimeout\([^)]*highlight/i.test(src), 'no second highlight-expiry timer -- the only timer for this must remain inside workbenchSyncCore.js, not OrderManage.vue')
})

test('3. The new-order badge and tile ring use the file\'s own existing amber vocabulary, not a new color/token', () => {
  // Accepts either the original inline-style tag, or the later refactor that
  // moved repeated inline styles into a shared class (order-tag-new) -- both
  // are fine as long as the "新" tag still renders with the exact same amber
  // already used by printStatus === 'unknown' (order-tag-print-unknown), not
  // a second, drifted color.
  const inlineMatch = src.includes("background:#fffbeb;color:#b45309;border-color:#fde68a;font-size:10px;font-weight:700\">新</a-tag>")
  const classMatch = /class="order-tag-new">新<\/a-tag>/.test(src)
  assert.ok(inlineMatch || classMatch, 'the "新" tag must be styled with either the exact inline amber style, or the order-tag-new class')
  if (classMatch) {
    const sharedRuleMatch = src.match(/\.order-tag-new,\s*\n\s*\.order-tag-print-unknown\s*\{([^}]*)\}/)
    assert.ok(sharedRuleMatch, 'order-tag-new must share its color rule with order-tag-print-unknown, not define its own separate amber')
    const rule = sharedRuleMatch[1]
    assert.ok(rule.includes('#fffbeb') && rule.includes('#b45309') && rule.includes('#fde68a'), 'the shared order-tag-new/order-tag-print-unknown rule must use the exact amber tag style already used elsewhere in this file (e.g. printStatus === \'unknown\')')
  }
  assert.ok(src.includes('.table-tile--new {') , 'the grid-tile new-order ring must be a real CSS rule')
  const tileNewRule = slice('.table-tile--new {', '}')
  assert.ok(tileNewRule.includes('#f59e0b'), 'the tile ring must reuse the same amber (#f59e0b) already used by .table-tile--urgent, not invent a new color')
})

test('4. useWorkbenchSync.js and the three staff workbenches are untouched -- Phase-05A only touches OrderManage.vue', () => {
  const repoRoot = path.resolve(root, '..')
  for (const file of ['src/composables/useWorkbenchSync.js', 'src/composables/workbenchSyncCore.js', 'src/views/FrontdeskWorkbench.vue', 'src/views/KitchenWorkbench.vue', 'src/views/WaiterWorkbench.vue']) {
    const gitShow = execSync(`git show HEAD:admin-h5/${file.replace(/\\/g, '/')}`, { cwd: repoRoot, encoding: 'utf8' }).replace(/\r\n/g, '\n')
    const current = fs.readFileSync(path.join(root, file), 'utf8').replace(/\r\n/g, '\n')
    assert.equal(current, gitShow, `${file} must be unchanged from the last commit (compared with line endings normalized) -- Phase-05A must not touch the shared highlight authority or its existing consumers`)
  }
})

// ---------------------------------------------------------------------------
// F2: reject-order confirmation.
// ---------------------------------------------------------------------------

test('5. Clicking reject no longer fires the business request directly -- it must go through a confirm dialog first', () => {
  const rejectOrderFn = slice('function rejectOrder(order) {', '\nasync function finishOrder')
  assert.ok(rejectOrderFn.includes('Modal.confirm({'), 'rejectOrder must open a confirmation dialog')
  const confirmCallIdx = rejectOrderFn.indexOf('Modal.confirm({')
  const apiCallIdx = rejectOrderFn.indexOf("updateOrderStatus(order.id, 'rejected')")
  assert.ok(confirmCallIdx !== -1 && apiCallIdx !== -1 && confirmCallIdx < apiCallIdx, 'the confirm dialog must be opened before the business request, and the business request must live inside it (structurally later in the function body)')
  const onOkBlock = rejectOrderFn.split('onOk: async () => {', 2)[1]
  assert.ok(onOkBlock, 'the business request must be wrapped in onOk, not fired eagerly when rejectOrder() is called')
  assert.ok(onOkBlock.indexOf("updateOrderStatus(order.id, 'rejected')") < onOkBlock.indexOf('},\n  })'), 'the update call must be inside the onOk callback body, not after Modal.confirm returns')
})

test('6. Cancelling the reject confirmation cannot call the API or touch order state', () => {
  const rejectOrderFn = slice('function rejectOrder(order) {', '\nasync function finishOrder')
  // Everything that mutates state or calls the API must live strictly inside onOk;
  // nothing between "Modal.confirm({" and "onOk:" may touch order.updating or the API.
  const beforeOnOk = rejectOrderFn.split('onOk: async () => {', 1)[0]
  assert.ok(!beforeOnOk.includes('order.updating = true'), 'order.updating must not be set before the user confirms')
  assert.ok(!beforeOnOk.includes('updateOrderStatus'), 'updateOrderStatus must not be reachable before the user confirms')
  assert.ok(beforeOnOk.includes("cancelText: '再想想'"), 'a cancel path must exist and be labeled, confirming Modal.confirm (not a fire-and-forget call) governs this action')
})

test('7. Confirming reject still uses the exact original business path -- same API call, same success/refund/error handling, same reconcile', () => {
  const rejectOrderFn = slice('function rejectOrder(order) {', '\nasync function finishOrder')
  const onOkBlock = rejectOrderFn.split('onOk: async () => {', 2)[1]
  assert.ok(onOkBlock.includes("const res = await updateOrderStatus(order.id, 'rejected')"), 'must call the same status-update endpoint with the same status value')
  // P0-PAID-PENDING: the unpaid success feedback is unchanged; a paid order now
  // also gets a success toast that points to the follow-up refund step.
  assert.ok(onOkBlock.includes("'已拒单，请联系顾客说明原因'"), 'the original unpaid success feedback text must be preserved')
  assert.ok(onOkBlock.includes("'已拒单，请继续点击“退款”完成退款'"), 'a paid reject must guide the merchant to the refund step')
  assert.ok(onOkBlock.includes("res?.data?.code === 'PAID_ORDER_CANCEL_REQUIRES_REFUND'"), 'the paid-order-requires-refund business rule must be preserved unchanged')
  assert.ok(onOkBlock.includes('await reconcileAfterOrderAction()'), 'must still reconcile through the existing sync path (Phase-03A truthfulness contract), not apply a local optimistic mutation')
  assert.ok(!onOkBlock.includes('order.status ='), 'must not directly assign order.status -- truth still comes from reconcileAfterOrderAction/syncNow, not a local write')
})

test('8. Reject button wiring in the template is unchanged -- no new click target, no new component', () => {
  const rejectButtons = [...src.matchAll(/@click="rejectOrder\(order\)"/g)]
  assert.equal(rejectButtons.length, 2, 'both order-card locations (list view + table drawer) must still call rejectOrder(order) directly -- the confirm step lives inside the function, not a second wrapper in the template')
})

if (failures.length) {
  console.error(`Phase-05A RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-05A order high-frequency efficiency: passed')
