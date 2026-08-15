import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const corePath = path.join(root, 'src/composables/workbenchSyncCore.js')
const core = await import(pathToFileURL(corePath).href)

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8')
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function fakeTimers() {
  let nextId = 1
  const timers = new Map()
  return {
    setTimeoutFn(fn, delay) {
      const id = nextId++
      timers.set(id, { fn, delay })
      return id
    },
    clearTimeoutFn(id) {
      timers.delete(id)
    },
    nextDelay() {
      return [...timers.values()][0]?.delay ?? null
    },
    runNext() {
      const entry = [...timers.entries()][0]
      if (!entry) return
      timers.delete(entry[0])
      entry[1].fn()
    },
  }
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
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

await test('R01 owner foreground uses delta instead of five-second full orders polling', () => {
  const source = read('src/views/OrderManage.vue')
  assert.ok(source.includes('getOwnerOrderChanges'), 'Owner delta API must be wired')
  assert.ok(!source.includes("pollingManager.start('orders:today'"), 'legacy full polling must be removed')
})

await test('R02 owner alert membership is based on actionable order identity', () => {
  assert.equal(typeof core.ownerActionableIdsFromOrders, 'function')
  const before = core.ownerActionableIdsFromOrders([
    { id: 'A', status: 'pending' },
    { id: 'B', status: 'pending' },
    { id: 'P', status: 'pending_payment' },
  ])
  const after = core.ownerActionableIdsFromOrders([
    { id: 'B', status: 'preparing' },
    { id: 'C', status: 'pending' },
    { id: 'P', status: 'pending' },
  ])
  assert.deepEqual(core.diffNewPendingIds(before, after).sort(), ['C', 'P'])
})

await test('R02 duplicate delta rows collapse to one row and at most one alert', async () => {
  let sounds = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => ({ orders: [], cursor: 'C0' }),
    fetchChanges: async () => ({
      items: [
        { id: 'D1', status: 'pending' },
        { id: 'D1', status: 'pending' },
        { id: 'D1', status: 'pending' },
      ],
      removed_ids: [],
      next_cursor: 'C1',
      has_more: false,
    }),
    filterOrders: (orders) => orders,
    alertIdsFromOrders: core.ownerActionableIdsFromOrders,
    playSound: () => { sounds += 1 },
    setTimeoutFn: () => 1,
    clearTimeoutFn: () => {},
  })
  sync.start()
  await flush()
  await sync.syncDelta()
  assert.equal(sync.getState().orders.length, 1)
  assert.equal(sync.getState().orders[0].id, 'D1')
  assert.equal(sounds, 1)
  await sync.syncDelta()
  assert.equal(sync.getState().orders.length, 1)
  assert.equal(sounds, 1)
  sync.stop()
})

await test('R03 tenant or auth identity change discards the late response', async () => {
  const first = deferred()
  let identity = 'tenant-a:token-a'
  let calls = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => {
      calls += 1
      if (calls === 1) return first.promise
      return { orders: [{ id: 'B', status: 'pending' }], cursor: 'B1' }
    },
    fetchChanges: async () => ({ items: [], removed_ids: [], next_cursor: 'B1', has_more: false }),
    filterOrders: (orders) => orders,
    getIdentity: () => identity,
  })
  sync.start()
  identity = 'tenant-b:token-b'
  first.resolve({ orders: [{ id: 'A', status: 'pending' }], cursor: 'A1' })
  await flush()
  await flush()
  assert.deepEqual(sync.getState().orders.map((order) => order.id), ['B'])
  sync.stop()
})

await test('R04 stop prevents a late response from applying or emitting again', async () => {
  const pending = deferred()
  let changes = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: () => pending.promise,
    filterOrders: (orders) => orders,
    onChange: () => { changes += 1 },
  })
  sync.start()
  sync.stop()
  const changesAtStop = changes
  pending.resolve({ orders: [{ id: 'late', status: 'pending' }], cursor: 'L1' })
  await flush()
  assert.deepEqual(sync.getState().orders, [])
  assert.equal(changes, changesAtStop)
})

await test('R03 late auth error from the old identity cannot stop the new session', async () => {
  const first = deferred()
  let identity = 'tenant-a:token-a'
  let calls = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => {
      calls += 1
      if (calls === 1) return first.promise
      return { orders: [{ id: 'B', status: 'pending' }], cursor: 'B1' }
    },
    filterOrders: (orders) => orders,
    getIdentity: () => identity,
  })
  sync.start()
  identity = 'tenant-b:token-b'
  const error = new Error('old unauthorized')
  error.response = { status: 401 }
  first.reject(error)
  await flush()
  await flush()
  assert.equal(sync.getState().authStopped, false)
  assert.deepEqual(sync.getState().orders.map((order) => order.id), ['B'])
  sync.stop()
})

await test('R03 auth-stopped session restarts when tenant or token identity changes', async () => {
  let identity = 'tenant-a:token-a'
  let calls = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => {
      calls += 1
      if (calls === 1) {
        const error = new Error('expired')
        error.response = { status: 401 }
        throw error
      }
      return { orders: [{ id: 'B', status: 'pending' }], cursor: 'B1' }
    },
    filterOrders: (orders) => orders,
    getIdentity: () => identity,
  })
  sync.start()
  await flush()
  assert.equal(sync.getState().authStopped, true)
  identity = 'tenant-b:token-b'
  await sync.syncNow()
  assert.equal(calls, 2)
  assert.equal(sync.getState().authStopped, false)
  assert.deepEqual(sync.getState().orders.map((order) => order.id), ['B'])
  sync.stop()
})

await test('R04 stop also suppresses a late rejected request', async () => {
  const pending = deferred()
  let changes = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: () => pending.promise,
    filterOrders: (orders) => orders,
    onChange: () => { changes += 1 },
  })
  sync.start()
  sync.stop()
  const changesAtStop = changes
  pending.reject(new Error('late network error'))
  await flush()
  assert.equal(changes, changesAtStop)
  assert.equal(sync.getState().syncFailed, false)
})

await test('R05 consecutive sync failures back off and success resets cadence', async () => {
  const timers = fakeTimers()
  let calls = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: async () => {
      calls += 1
      if (calls <= 2) throw new Error('network')
      return { orders: [], cursor: 'OK' }
    },
    filterOrders: (orders) => orders,
    intervalMs: 5000,
    setTimeoutFn: timers.setTimeoutFn,
    clearTimeoutFn: timers.clearTimeoutFn,
  })
  sync.start()
  await flush()
  assert.equal(timers.nextDelay(), 5000)
  timers.runNext()
  await flush()
  assert.equal(timers.nextDelay(), 10000)
  timers.runNext()
  await flush()
  assert.equal(timers.nextDelay(), 5000)
  sync.stop()
})

await test('R06 pageshow performs immediate reconciliation through the sync core', () => {
  const source = read('src/composables/useWorkbenchSync.js')
  assert.ok(source.includes("addEventListener('pageshow'"))
  assert.ok(source.includes("removeEventListener('pageshow'"))
})

await test('R07 owner status actions reconcile instead of applying response status as authority', () => {
  const source = read('src/views/OrderManage.vue')
  assert.ok(source.includes('reconcileAfterOrderAction'))
  assert.ok(!/if \(res\.code === 200\) order\.status = ['"]/.test(source))
  const pickupAction = source.split('async function handlePickupSelect(n)', 2)[1].split('async function ensureStaffNewTablesLoaded()', 1)[0]
  assert.ok(!pickupAction.includes('applyPickupNoToOrders('), 'pickup action must not apply its response over sync truth')
  assert.ok(pickupAction.includes('await reconcileAfterOrderAction()'))
})

await test('R07 action reconciliation waits for a queued authoritative full', async () => {
  const first = deferred()
  const second = deferred()
  let calls = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: () => (++calls === 1 ? first.promise : second.promise),
    filterOrders: (orders) => orders,
  })
  sync.start()
  let reconciled = false
  const barrier = sync.syncNow().then(() => { reconciled = true })
  await flush()
  assert.equal(reconciled, false)
  first.resolve({ orders: [{ id: 'old', status: 'pending' }], cursor: 'C1' })
  await flush()
  await flush()
  assert.equal(calls, 2)
  assert.equal(reconciled, false)
  second.resolve({ orders: [{ id: 'new', status: 'preparing' }], cursor: 'C2' })
  await barrier
  assert.deepEqual(sync.getState().orders.map((order) => order.id), ['new'])
  sync.stop()
})

await test('R07 each queued action barrier is bound to its own following full', async () => {
  const requests = [deferred(), deferred(), deferred()]
  let calls = 0
  const sync = core.createWorkbenchSyncCore({
    fetchFull: () => requests[calls++].promise,
    filterOrders: (orders) => orders,
  })
  sync.start()
  let firstBarrierDone = false
  let secondBarrierDone = false
  const firstBarrier = sync.syncNow().then(() => { firstBarrierDone = true })
  requests[0].resolve({ orders: [{ id: 'F1', status: 'pending' }], cursor: 'F1' })
  await flush()
  await flush()
  assert.equal(calls, 2)
  const secondBarrier = sync.syncNow().then(() => { secondBarrierDone = true })
  requests[1].resolve({ orders: [{ id: 'F2', status: 'preparing' }], cursor: 'F2' })
  await flush()
  await flush()
  assert.equal(calls, 3)
  assert.equal(firstBarrierDone, true)
  assert.equal(secondBarrierDone, false)
  requests[2].resolve({ orders: [{ id: 'F3', status: 'done' }], cursor: 'F3' })
  await Promise.all([firstBarrier, secondBarrier])
  assert.deepEqual(sync.getState().orders.map((order) => order.id), ['F3'])
  sync.stop()
})

await test('Owner initial full remains ordered after payment-mode initialization', () => {
  const source = read('src/views/OrderManage.vue')
  assert.ok(source.includes('autoStart: false'))
  const mounted = source.split('onMounted(async () => {', 2)[1]
  assert.ok(mounted.indexOf('await loadPaymentMode()') < mounted.indexOf('startSync()'))
})

if (failures.length) {
  console.error(`P0-08 RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('P0-08 Admin reliability contracts: passed')
