/**
 * Phase 4A: workbench auto-sync + new-pending ID detection.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const coreUrl = pathToFileURL(path.join(root, 'src/composables/workbenchSyncCore.js')).href
const {
  WORKBENCH_SYNC_INTERVAL_MS,
  createWorkbenchSyncCore,
  diffNewPendingIds,
  pendingIdsFromOrders,
} = await import(coreUrl)

function read(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8')
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

assert.equal(WORKBENCH_SYNC_INTERVAL_MS, 5000)

// --- pure helpers ---
{
  const ids = pendingIdsFromOrders([
    { id: '7491803654157111296', status: 'pending' },
    { id: '2', status: 'preparing' },
    { id: 3, status: 'pending' },
  ])
  assert.ok(ids.has('7491803654157111296'))
  assert.ok(ids.has('3'))
  assert.equal(ids.has('2'), false)
}

{
  const known = new Set(['A', 'B'])
  const current = new Set(['B', 'C'])
  assert.deepEqual(diffNewPendingIds(known, current), ['C'])
}

// Fake timer helpers
function createFakeTimers() {
  let nextId = 1
  const timers = new Map()
  let now = 1_000_000
  return {
    now: () => now,
    advance(ms) {
      now += ms
      const due = [...timers.entries()].filter(([, t]) => t.when <= now)
      due.sort((a, b) => a[1].when - b[1].when)
      for (const [id, t] of due) {
        timers.delete(id)
        t.fn()
      }
    },
    setTimeoutFn(fn, ms) {
      const id = nextId++
      timers.set(id, { fn, when: now + ms })
      return id
    },
    clearTimeoutFn(id) {
      timers.delete(id)
    },
    pendingCount: () => timers.size,
  }
}

async function withCore(fetchImpl, extras = {}) {
  const timers = createFakeTimers()
  let sounds = 0
  let snapshot = null
  const core = createWorkbenchSyncCore({
    fetchOrders: fetchImpl,
    filterOrders: (raw) => raw.filter((o) => ['pending', 'preparing', 'done'].includes(o.status)),
    playSound: () => {
      sounds += 1
    },
    now: timers.now,
    setTimeoutFn: timers.setTimeoutFn,
    clearTimeoutFn: timers.clearTimeoutFn,
    onChange: (s) => {
      snapshot = s
    },
    ...extras,
  })
  return { core, timers, getSounds: () => sounds, getSnapshot: () => snapshot }
}

let fetchCount = 0
let payload = [
  { id: 'A', status: 'pending' },
  { id: 'B', status: 'pending' },
  { id: 'C', status: 'pending' },
]

const { core, timers, getSounds, getSnapshot } = await withCore(async () => {
  fetchCount += 1
  if (payload instanceof Error) throw payload
  return payload.map((o) => ({ ...o }))
})

// TEST-01 mount/start → 1 request
core.start()
await sleep(0)
assert.equal(fetchCount, 1)
assert.equal(getSounds(), 0, 'TEST-07 first baseline no sound')
assert.deepEqual([...getSnapshot().knownPendingIds].sort(), ['A', 'B', 'C'])

// TEST-02 visible schedule → next request after 5s
timers.advance(5000)
await sleep(0)
assert.equal(fetchCount, 2)

// TEST-03 hidden → no further schedule polling
core.setVisible(false)
const afterHidden = fetchCount
timers.advance(5000)
await sleep(0)
assert.equal(fetchCount, afterHidden, 'hidden must pause polling')

// TEST-04 visible → immediate request
core.setVisible(true)
await sleep(0)
assert.equal(fetchCount, afterHidden + 1)

// TEST-05 offline then online
core.setOnline(false)
const afterOff = fetchCount
timers.advance(5000)
await sleep(0)
assert.equal(fetchCount, afterOff)
core.setOnline(true)
await sleep(0)
assert.equal(fetchCount, afterOff + 1)

// TEST-06 in-flight overlap skip
{
  let calls = 0
  let resolveFetch
  const gate = new Promise((r) => {
    resolveFetch = r
  })
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => {
      calls += 1
      await gate
      return [{ id: 'A', status: 'pending' }]
    },
    filterOrders: (raw) => raw,
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  const pStart = Promise.resolve()
  await sleep(0)
  const p2 = c.syncNow()
  const p3 = c.syncNow()
  assert.equal(calls, 1)
  resolveFetch()
  await pStart
  const r2 = await p2
  const r3 = await p3
  await sleep(0)
  assert.equal(calls, 1)
  assert.equal(r2.skipped, true)
  assert.equal(r3.skipped, true)
  assert.equal(c.getState().hasBaseline, true)
}

// Reset main core for new-order tests: stop and recreate
core.stop()
fetchCount = 0
payload = [
  { id: 'A', status: 'pending' },
  { id: 'B', status: 'pending' },
]
const round2 = await withCore(async () => {
  fetchCount += 1
  if (payload instanceof Error) throw payload
  return payload.map((o) => ({ ...o }))
})
round2.core.start()
await sleep(0)
assert.equal(round2.getSounds(), 0)

// TEST-08 A B → A B C
payload = [
  { id: 'A', status: 'pending' },
  { id: 'B', status: 'pending' },
  { id: 'C', status: 'pending' },
]
await round2.core.syncNow()
assert.deepEqual(round2.getSnapshot().lastNewIds, ['C'])
assert.equal(round2.getSounds(), 1)
assert.equal(round2.core.isHighlighted('C'), true)

// TEST-09 same count: A B → B C
payload = [
  { id: 'B', status: 'pending' },
  { id: 'C', status: 'pending' },
]
const soundsBefore = round2.getSounds()
await round2.core.syncNow()
// C already known from previous — no new sound. Need fresh known for this case.
assert.equal(round2.getSnapshot().lastNewIds.length, 0)

// Dedicated TEST-09
{
  let sounds = 0
  let data = [
    { id: 'A', status: 'pending' },
    { id: 'B', status: 'pending' },
  ]
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => data.map((o) => ({ ...o })),
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds += 1
    },
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  assert.equal(sounds, 0)
  data = [
    { id: 'B', status: 'pending' },
    { id: 'C', status: 'pending' },
  ]
  const r = await c.syncNow()
  assert.deepEqual(r.newIds, ['C'])
  assert.equal(sounds, 1)
}

// TEST-10 multi new → sound once
{
  let sounds = 0
  let data = [{ id: 'A', status: 'pending' }]
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => data.map((o) => ({ ...o })),
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds += 1
    },
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  data = [
    { id: 'A', status: 'pending' },
    { id: 'B', status: 'pending' },
    { id: 'C', status: 'pending' },
    { id: 'D', status: 'pending' },
  ]
  const r = await c.syncNow()
  assert.equal(r.newIds.length, 3)
  assert.equal(sounds, 1)
}

// TEST-11 pending→preparing not new
{
  let sounds = 0
  let data = [{ id: 'A', status: 'pending' }]
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => data.map((o) => ({ ...o })),
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds += 1
    },
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  data = [{ id: 'A', status: 'preparing' }]
  const r = await c.syncNow()
  assert.deepEqual(r.newIds, [])
  assert.equal(sounds, 0)
}

// TEST-12 error keeps snapshot
{
  let sounds = 0
  let fail = false
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => {
      if (fail) {
        const err = new Error('network')
        throw err
      }
      return [
        { id: 'A', status: 'pending' },
        { id: 'B', status: 'pending' },
        { id: 'C', status: 'pending' },
      ]
    },
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds += 1
    },
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  const at = c.getState().lastSuccessfulSyncAt
  fail = true
  await c.syncNow()
  const st = c.getState()
  assert.equal(st.orders.length, 3)
  assert.equal(st.syncFailed, true)
  assert.equal(st.lastSuccessfulSyncAt, at)
  assert.equal(sounds, 0)

  // TEST-13 recover + new D
  fail = false
  let data = null
  const c2fetch = async () => {
    if (data) return data
    return [
      { id: 'A', status: 'pending' },
      { id: 'B', status: 'pending' },
      { id: 'C', status: 'pending' },
      { id: 'D', status: 'pending' },
    ]
  }
  // continue on same core with patched fetch by recreating known via sync success path:
  // swap by creating new core seeded manually is hard; just sync with fail=false on same
  // but fetch still returns ABC. Rebuild:
  let sounds2 = 0
  let phase = 'ok'
  const t2 = createFakeTimers()
  const c2 = createWorkbenchSyncCore({
    fetchOrders: async () => {
      if (phase === 'fail') throw new Error('network')
      if (phase === 'ok') {
        return [
          { id: 'A', status: 'pending' },
          { id: 'B', status: 'pending' },
          { id: 'C', status: 'pending' },
        ]
      }
      return [
        { id: 'A', status: 'pending' },
        { id: 'B', status: 'pending' },
        { id: 'C', status: 'pending' },
        { id: 'D', status: 'pending' },
      ]
    },
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds2 += 1
    },
    setTimeoutFn: t2.setTimeoutFn,
    clearTimeoutFn: t2.clearTimeoutFn,
    now: t2.now,
  })
  c2.start()
  await sleep(0)
  phase = 'fail'
  await c2.syncNow()
  phase = 'recover'
  const r = await c2.syncNow()
  assert.deepEqual(r.newIds, ['D'])
  assert.equal(c2.getState().syncFailed, false)
  assert.equal(sounds2, 1)
}

// TEST-14 sound throw must not break sync
{
  const t = createFakeTimers()
  let data = [{ id: 'A', status: 'pending' }]
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => data.map((o) => ({ ...o })),
    filterOrders: (raw) => raw,
    playSound: () => {
      throw new Error('audio blocked')
    },
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  data = [
    { id: 'A', status: 'pending' },
    { id: 'B', status: 'pending' },
  ]
  const r = await c.syncNow()
  assert.equal(r.ok, true)
  assert.deepEqual(r.newIds, ['B'])
  assert.equal(c.getState().orders.length, 2)
}

// TEST-17 FIFO preserved (no re-sort)
{
  const t = createFakeTimers()
  let data = [
    { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
    { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
  ]
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => data.map((o) => ({ ...o })),
    filterOrders: (raw) => raw,
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  data = [
    { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
    { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
    { id: 'C', status: 'pending', created_at: '2026-08-08T10:02:00Z' },
  ]
  await c.syncNow()
  assert.deepEqual(
    c.getState().orders.map((o) => o.id),
    ['A', 'B', 'C'],
  )
}

// 401 stops retries
{
  const t = createFakeTimers()
  let calls = 0
  const c = createWorkbenchSyncCore({
    fetchOrders: async () => {
      calls += 1
      const err = new Error('unauthorized')
      err.response = { status: 401 }
      throw err
    },
    filterOrders: (raw) => raw,
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  c.start()
  await sleep(0)
  assert.equal(calls, 1)
  t.advance(5000)
  await sleep(0)
  assert.equal(calls, 1, '401 must stop polling')
}

// Static wiring checks
const waiter = read('src/views/WaiterWorkbench.vue')
const kitchen = read('src/views/KitchenWorkbench.vue')
const useSync = read('src/composables/useWorkbenchSync.js')
const alert = read('src/composables/useOrderAlert.js')
const orderManage = read('src/views/OrderManage.vue')

assert.ok(waiter.includes('useWorkbenchSync'), 'Waiter wired')
assert.ok(kitchen.includes('useWorkbenchSync'), 'Kitchen wired')
assert.ok(waiter.includes('WorkbenchSyncBar'), 'Waiter status bar')
assert.ok(kitchen.includes('WorkbenchSyncBar'), 'Kitchen status bar')
assert.ok(waiter.includes('is-new') && waiter.includes('新'), 'Waiter highlight')
assert.ok(kitchen.includes('is-new') && kitchen.includes('新'), 'Kitchen highlight')
assert.ok(useSync.includes('visibilitychange'), 'visibility listener')
assert.ok(useSync.includes("addEventListener('online'"), 'online listener')
assert.ok(useSync.includes('playNewOrderBeep'), 'reuses alert beep')
assert.ok(alert.includes('playNewOrderBeep'), 'alert exports play')
assert.ok(alert.includes('isSoundReady'), 'alert exports readiness')
assert.ok(orderManage.includes('noteNewPendingCount'), 'Owner path kept')
assert.ok(orderManage.includes('useOrderAlert'), 'Owner still uses useOrderAlert')
assert.ok(!waiter.includes('WebSocket') && !kitchen.includes('EventSource'), 'no WS/SSE')
assert.ok(!useSync.includes('WebSocket'), 'sync has no WS')

console.log('TEST-FE workbenchSync: passed')
