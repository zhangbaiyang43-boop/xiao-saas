// Phase-03A acceptance suite: OrderManage state truthfulness.
//
// Locks the five scenarios required by
// docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03A_ORDER_STATE_MIGRATION.md so a future
// change to OrderManage.vue or workbenchSyncCore.js cannot silently regress them.
//
// Scenario 1-4 replay the real sync core (same module OrderManage.vue consumes) so the
// assertions are behavioral, not just "the string appears in the file". Scenario 5
// (unknown) is inherently about OrderManage's own print-status markup, so it is
// asserted against the component source directly, the same way scenario coverage
// already works in scripts/test-p0-08-sync.mjs.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const core = await import(pathToFileURL(path.join(root, 'src/composables/workbenchSyncCore.js')).href)

function readOrderManageSource() {
  return fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8')
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
}

// Mirrors the real computed in OrderManage.vue:
//   const orderLoadError = computed(() => syncFailed.value && orders.value.length === 0)
function orderLoadError(state) {
  return state.syncFailed && state.orders.length === 0
}

// Mirrors the real template condition:
//   v-else-if="!loading && !syncFailed && orders.length === 0"
function isEmptyState(state, loading) {
  return !loading && !state.syncFailed && state.orders.length === 0
}

const failures = []
async function test(name, fn) {
  try {
    await fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}

await test('1. First order sync failure resolves to Error, not Empty', async () => {
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => { throw new Error('network down') },
    filterOrders: (orders) => orders,
  })
  sync.start()
  await flush()
  const state = sync.getState()
  assert.equal(state.syncFailed, true, 'a failed first fetch must set syncFailed')
  assert.equal(state.orders.length, 0, 'a failed first fetch must not fabricate orders')
  assert.equal(orderLoadError(state), true, 'orderLoadError must be true so the page renders the error alert, not the empty state')
  assert.equal(isEmptyState(state, false), false, 'empty condition must be false when sync has failed')
  sync.stop()
})

await test('2. Order sync succeeding with zero orders resolves to Empty', async () => {
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => ({ orders: [], cursor: 'C0' }),
    filterOrders: (orders) => orders,
  })
  sync.start()
  await flush()
  const state = sync.getState()
  assert.equal(state.syncFailed, false, 'a successful empty fetch must not be flagged as failed')
  assert.equal(state.orders.length, 0)
  assert.equal(orderLoadError(state), false, 'a real empty result must not render as an error')
  assert.equal(isEmptyState(state, false), true, 'empty condition must be true only for a confirmed, successful zero-result sync')
  sync.stop()
})

await test('3. A refresh failure after a prior success preserves existing orders and reports failure', async () => {
  let call = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => {
      call += 1
      if (call === 1) return { orders: [{ id: 'A', status: 'pending' }, { id: 'B', status: 'pending' }], cursor: 'C0' }
      throw new Error('refresh failed')
    },
    filterOrders: (orders) => orders,
  })
  sync.start()
  await flush()
  assert.deepEqual(sync.getState().orders.map((o) => o.id), ['A', 'B'])

  const result = await sync.syncNow()
  assert.equal(result.ok, false, 'a failed manual refresh must report ok:false so the page shows a failure, not a false success toast')
  const afterFailure = sync.getState()
  assert.equal(afterFailure.syncFailed, true)
  assert.deepEqual(afterFailure.orders.map((o) => o.id), ['A', 'B'], 'existing orders must not be cleared just because the refresh failed')
  sync.stop()

  const source = readOrderManageSource()
  assert.ok(source.includes('v-if="syncFailed && orders.length > 0"'), 'a persistent banner (not only a toast) must cover the stale-but-visible-data case')
  const manualRefresh = source.split('async function manualRefresh() {', 2)[1].split('const pendingCount', 1)[0]
  assert.ok(manualRefresh.includes("if (result?.ok !== true)"), 'manualRefresh must gate the success toast on an acknowledged successful sync')
  assert.ok(manualRefresh.indexOf('message.error') < manualRefresh.indexOf("message.success('已刷新'"), 'failure path must be checked before the success toast can fire')
})

await test('4. Order sync succeeding with data resolves to Success', async () => {
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => ({ orders: [{ id: 'A', status: 'pending' }], cursor: 'C0' }),
    filterOrders: (orders) => orders,
  })
  sync.start()
  await flush()
  const state = sync.getState()
  assert.equal(state.syncFailed, false)
  assert.equal(state.orders.length, 1)
  assert.equal(orderLoadError(state), false)
  assert.equal(isEmptyState(state, false), false)
  sync.stop()
})

await test('5. Unrecoverable-but-not-confirmed-failed print result renders as Unknown, not Success or Error', () => {
  const source = readOrderManageSource()
  const unknownTagMatches = [...source.matchAll(/order\.printStatus === 'unknown'[\s\S]{0,140}?<\/a-tag>/g)]
  assert.ok(unknownTagMatches.length >= 1, 'printStatus unknown must have its own dedicated tag markup')
  for (const match of unknownTagMatches) {
    const markup = match[0]
    assert.ok(markup.includes('打印结果未知'), 'unknown print result must say it is unknown, not imply success or failure')
    assert.ok(!markup.includes('#07C160') && !markup.includes('#16a34a'), 'unknown state must not borrow the success green used elsewhere in this file')
    assert.ok(!markup.includes('#dc2626') && !markup.includes('#fef2f2'), 'unknown state must not borrow the failed-print red used for printStatus === "failed" in this same file')
  }
  assert.ok(source.includes("['failed','unknown'].includes(order.printStatus)"), 'unknown must be treated as needing recovery (reprint entry) same as a confirmed failure, without claiming the print itself failed')
})

if (failures.length) {
  console.error(`Phase-03A RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-03A order state truthfulness: passed')
