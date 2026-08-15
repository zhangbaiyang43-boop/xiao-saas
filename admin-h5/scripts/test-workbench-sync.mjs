/**
 * Phase 4A/4C: workbench sync — full baseline, 5s delta, 60s full reconcile.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const coreUrl = pathToFileURL(path.join(root, 'src/composables/workbenchSyncCore.js')).href
const {
  WORKBENCH_FULL_RECONCILE_INTERVAL_MS,
  WORKBENCH_SYNC_INTERVAL_MS,
  applyWorkbenchDelta,
  createWorkbenchSyncCore,
  diffNewPendingIds,
  needsPickupIdsFromOrders,
  pendingIdsFromOrders,
  sortOrdersFifo,
  waitingToServeIdsFromOrders,
} = await import(coreUrl)

function read(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8')
}

function countText(source, text) {
  return source.split(text).length - 1
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

assert.equal(WORKBENCH_SYNC_INTERVAL_MS, 5000)
assert.equal(WORKBENCH_FULL_RECONCILE_INTERVAL_MS, 60000)

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

{
  const ids = needsPickupIdsFromOrders([
    { id: '1', can_assign_pickup_no: true, pickup_no: '' },
    { id: '2', can_assign_pickup_no: true, pickup_no: '8' },
    { id: '3', can_assign_pickup_no: false, pickup_no: '' },
  ])
  assert.ok(ids.has('1'))
  assert.equal(ids.has('2'), false)
  assert.equal(ids.has('3'), false)
}

{
  const ids = waitingToServeIdsFromOrders([
    { id: '1', status: 'done', served_at: null },
    { id: '2', status: 'done', served_at: '2026-08-09T00:00:00Z' },
    { id: '3', status: 'pending', served_at: null },
  ])
  assert.ok(ids.has('1'))
  assert.equal(ids.has('2'), false)
  assert.equal(ids.has('3'), false)
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

// TEST-06 overlapping Full requests coalesce behind one authoritative barrier
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
  assert.equal(calls, 2)
  assert.equal(r2.ok, true)
  assert.equal(r3.ok, true)
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
const frontdesk = read('src/views/FrontdeskWorkbench.vue')
const useSync = read('src/composables/useWorkbenchSync.js')
const alert = read('src/composables/useOrderAlert.js')
const orderManage = read('src/views/OrderManage.vue')
const routerSrc = read('src/router/index.js')

assert.ok(waiter.includes('useWorkbenchSync'), 'Waiter wired')
assert.ok(kitchen.includes('useWorkbenchSync'), 'Kitchen wired')
assert.ok(frontdesk.includes('useWorkbenchSync'), 'Frontdesk wired')
assert.ok(waiter.includes('WorkbenchSyncBar'), 'Waiter status bar')
assert.ok(kitchen.includes('WorkbenchSyncBar'), 'Kitchen status bar')
assert.ok(frontdesk.includes('WorkbenchSyncBar'), 'Frontdesk status bar')
assert.ok(waiter.includes('waitingToServeIdsFromOrders'), 'Waiter R2: serving alerts')
assert.ok(waiter.includes('确认已上菜'), 'Waiter serve CTA')
assert.ok(waiter.includes('serveOrder'), 'Waiter serve API')
assert.ok(waiter.includes('getRecentServedByMe'), 'Waiter recent served API')
assert.ok(waiter.includes('最近已上菜'), 'Waiter recent served section')
assert.ok(waiter.includes('servingLabel(order)'), 'Waiter success toast includes table/pickup context')
assert.ok(waiter.includes('上菜确认失败，请重试'), 'Waiter failure copy is explicit')
assert.equal(countText(waiter, '顾客加菜'), 1, 'Waiter has exactly one customer add entry')
assert.equal(countText(waiter, '代客加单'), 0, 'Waiter removes assisted add wording')
assert.ok(!waiter.includes('ao-entry'), 'Waiter cards do not show assisted add button')
assert.ok(!waiter.includes('>刷新<'), 'Waiter refresh is not a main button')
assert.ok(waiter.includes('sync-link'), 'Waiter refresh is downgraded near sync status')
assert.ok(!waiter.includes('>退出<'), 'Waiter logout is not a main button')
assert.ok(waiter.includes('more-menu'), 'Waiter logout is downgraded into a light menu')
assert.ok(waiter.includes('待上菜'), 'Waiter job-first title')
assert.ok(!waiter.includes('接单') && !waiter.includes('发桌牌') && !waiter.includes('换桌牌'), 'Waiter non-serve actions removed')
assert.ok(kitchen.includes('is-new') && kitchen.includes('新'), 'Kitchen highlight')
assert.ok(kitchen.includes('待制作'), 'Kitchen job-first title')
assert.ok(!kitchen.includes('AssistedOrderSheet'), 'Kitchen no assisted add UI')
assert.ok(frontdesk.includes('needsPickupIdsFromOrders'), 'Frontdesk alerts on needs-pickup')
assert.ok(frontdesk.includes('发桌牌') && frontdesk.includes('换桌牌'), 'Frontdesk pickup actions')
assert.ok(frontdesk.includes('AssistedOrderSheet') && frontdesk.includes('代客加单'), 'Frontdesk R3 assisted add')
assert.ok(frontdesk.includes('待发牌'), 'Frontdesk job-first title')
assert.ok(!frontdesk.includes('接单') && !frontdesk.includes('补打厨房单'), 'Frontdesk no kitchen actions')
assert.ok(!frontdesk.includes('确认已上菜'), 'Frontdesk no serve CTA')
const assisted = read('src/components/AssistedOrderSheet.vue')
assert.ok(assisted.includes('title=\"顾客加菜\"'), 'Assisted sheet uses customer add wording')
assert.ok(assisted.includes('生成付款码'), 'Prepay staff-assisted add generates payment handoff')
assert.ok(assisted.includes('请顾客扫码付款'), 'Prepay staff-assisted add tells staff to ask customer to pay')
assert.ok(assisted.includes('createPaymentHandoff'), 'Prepay staff-assisted add creates payment handoff')
assert.ok(assisted.includes('ao-pay-card'), 'Payment handoff is shown in the assisted sheet')
assert.ok(!assisted.includes('placeholder="请输入桌号"'), 'R3 no table text input')
assert.ok(assisted.includes('ao-table-card'), 'R3 click table cards')
assert.ok(assisted.includes('确认加单'), 'R3 confirm CTA')
assert.ok(assisted.includes('request_id'), 'R3 idempotency key')
assert.ok(assisted.includes('其他备注'), 'R3 other remark exception path')
assert.ok(routerSrc.includes("path: 'frontdesk'"), 'Frontdesk route')
assert.ok(useSync.includes('visibilitychange'), 'visibility listener')
assert.ok(useSync.includes("addEventListener('online'"), 'online listener')
assert.ok(useSync.includes('playNewOrderBeep'), 'reuses alert beep')
assert.ok(alert.includes('playNewOrderBeep'), 'alert exports play')
assert.ok(alert.includes('isSoundReady'), 'alert exports readiness')
assert.ok(orderManage.includes('ownerActionableIdsFromOrders'), 'Owner alerts use actionable order IDs')
assert.ok(orderManage.includes('getOwnerOrderChanges'), 'Owner frequent sync uses delta')
assert.ok(orderManage.includes('useWorkbenchSync'), 'Owner reuses the reliable sync lifecycle')
assert.ok(!waiter.includes('WebSocket') && !kitchen.includes('EventSource'), 'no WS/SSE')
assert.ok(!useSync.includes('WebSocket'), 'sync has no WS')
assert.ok(useSync.includes('fetchChanges') || useSync.includes('getWorkbenchOrderChanges'), 'delta wired')
assert.ok(useSync.includes('WORKBENCH_FULL_RECONCILE_INTERVAL_MS'), '60s full wired')
assert.ok(useSync.includes('getWorkbenchOrdersWithCursor'), 'full cursor wired')
assert.ok(!useSync.includes('EventSource'), 'no SSE')

const apiSrc = read('src/api/index.js')
assert.ok(apiSrc.includes('/v1/orders/workbench/changes'), 'changes API')
assert.ok(apiSrc.includes('serveOrder') && apiSrc.includes('/serve'), 'serve API client')
assert.ok(apiSrc.includes('getActiveDiningSessions'), 'active dining sessions API client')

// --- Phase 4C delta helpers ---
{
  const base = [
    { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
    { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
  ]
  const next = applyWorkbenchDelta(
    base,
    [{ id: 'C', status: 'pending', created_at: '2026-08-08T10:02:00Z' }],
    [],
    (raw) => raw,
  )
  assert.deepEqual(
    next.map((o) => o.id),
    ['A', 'B', 'C'],
  )
  const removed = applyWorkbenchDelta(next, [], ['A'], (raw) => raw)
  assert.deepEqual(
    removed.map((o) => o.id),
    ['B', 'C'],
  )
  const upsert = applyWorkbenchDelta(
    removed,
    [{ id: 'B', status: 'preparing', created_at: '2026-08-08T10:01:00Z' }],
    [],
    (raw) => raw,
  )
  assert.equal(upsert.find((o) => o.id === 'B').status, 'preparing')
  assert.equal(upsert.filter((o) => o.id === 'B').length, 1)
  assert.deepEqual(
    sortOrdersFifo([
      { id: 'C', created_at: '2026-08-08T10:02:00Z' },
      { id: 'A', created_at: '2026-08-08T10:00:00Z' },
    ]).map((o) => o.id),
    ['A', 'C'],
  )
}

// Phase 4C: initial full + 5s delta + 60s full
{
  let fullCalls = 0
  let deltaCalls = 0
  let cursor = 'C0'
  let fullData = [
    { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
    { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
  ]
  let deltaPage = {
    items: [],
    removed_ids: [],
    next_cursor: 'C1',
    has_more: false,
  }
  let sounds = 0
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchFull: async () => {
      fullCalls += 1
      return { orders: fullData.map((o) => ({ ...o })), cursor }
    },
    fetchChanges: async (cur) => {
      deltaCalls += 1
      assert.equal(cur, cursor)
      const page = {
        items: deltaPage.items.map((o) => ({ ...o })),
        removed_ids: [...deltaPage.removed_ids],
        next_cursor: deltaPage.next_cursor,
        has_more: deltaPage.has_more,
      }
      cursor = page.next_cursor
      return page
    },
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds += 1
    },
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
    fullIntervalMs: 60000,
  })
  c.start()
  await sleep(0)
  assert.equal(fullCalls, 1)
  assert.equal(deltaCalls, 0)
  assert.equal(sounds, 0, 'initial baseline no sound')

  // 5s → delta no-change
  cursor = 'C0'
  c.getState().cursor // ensure set from full
  // restore cursor after fetchFull set it to C0
  t.advance(5000)
  await sleep(0)
  assert.equal(deltaCalls, 1)
  assert.equal(fullCalls, 1)

  // delta new pending C → sound once
  deltaPage = {
    items: [{ id: 'C', status: 'pending', created_at: '2026-08-08T10:02:00Z' }],
    removed_ids: [],
    next_cursor: 'C2',
    has_more: false,
  }
  t.advance(5000)
  await sleep(0)
  assert.equal(deltaCalls, 2)
  assert.equal(sounds, 1)
  assert.ok(c.isHighlighted('C'))
  assert.deepEqual(
    c.getState().orders.map((o) => o.id),
    ['A', 'B', 'C'],
  )

  // removed A
  deltaPage = {
    items: [],
    removed_ids: ['A'],
    next_cursor: 'C3',
    has_more: false,
  }
  const soundsBeforeRemove = sounds
  t.advance(5000)
  await sleep(0)
  assert.deepEqual(
    c.getState().orders.map((o) => o.id),
    ['B', 'C'],
  )
  assert.equal(sounds, soundsBeforeRemove, 'removal must not sound')

  // delta failure does not advance cursor
  const cFail = createWorkbenchSyncCore({
    fetchFull: async () => ({
      orders: [{ id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' }],
      cursor: 'CX',
    }),
    fetchChanges: async () => {
      const err = new Error('network')
      throw err
    },
    filterOrders: (raw) => raw,
    setTimeoutFn: t.setTimeoutFn,
    clearTimeoutFn: t.clearTimeoutFn,
    now: t.now,
  })
  cFail.start()
  await sleep(0)
  const cur1 = cFail.getState().cursor
  await cFail.sync('delta')
  assert.equal(cFail.getState().cursor, cur1)
  assert.equal(cFail.getState().syncFailed, true)

  // invalid cursor → full
  let full2 = 0
  const t3 = createFakeTimers()
  const c3 = createWorkbenchSyncCore({
    fetchFull: async () => {
      full2 += 1
      return {
        orders: [{ id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' }],
        cursor: 'GOOD',
      }
    },
    fetchChanges: async () => {
      const err = new Error('bad cursor')
      err.response = { status: 400, data: { code: 400, msg: 'INVALID_CURSOR' } }
      throw err
    },
    filterOrders: (raw) => raw,
    setTimeoutFn: t3.setTimeoutFn,
    clearTimeoutFn: t3.clearTimeoutFn,
    now: t3.now,
  })
  c3.start()
  await sleep(0)
  assert.equal(full2, 1)
  await c3.sync('delta')
  assert.equal(full2, 2)

  // pagination drain
  let pages = 0
  const t4 = createFakeTimers()
  const c4 = createWorkbenchSyncCore({
    fetchFull: async () => ({
      orders: [{ id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' }],
      cursor: 'P0',
    }),
    fetchChanges: async () => {
      pages += 1
      if (pages === 1) {
        return {
          items: [{ id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' }],
          removed_ids: [],
          next_cursor: 'P1',
          has_more: true,
        }
      }
      if (pages === 2) {
        return {
          items: [{ id: 'C', status: 'pending', created_at: '2026-08-08T10:02:00Z' }],
          removed_ids: [],
          next_cursor: 'P2',
          has_more: true,
        }
      }
      return {
        items: [{ id: 'D', status: 'pending', created_at: '2026-08-08T10:03:00Z' }],
        removed_ids: [],
        next_cursor: 'P3',
        has_more: false,
      }
    },
    filterOrders: (raw) => raw,
    setTimeoutFn: t4.setTimeoutFn,
    clearTimeoutFn: t4.clearTimeoutFn,
    now: t4.now,
  })
  c4.start()
  await sleep(0)
  await c4.sync('delta')
  assert.equal(pages, 3)
  assert.deepEqual(
    c4.getState().orders.map((o) => o.id),
    ['A', 'B', 'C', 'D'],
  )
  assert.equal(c4.getState().cursor, 'P3')

  // 60s periodic full repairs missed pending
  let sounds5 = 0
  let full5 = 0
  const t5 = createFakeTimers()
  const c5 = createWorkbenchSyncCore({
    fetchFull: async () => {
      full5 += 1
      if (full5 === 1) {
        return {
          orders: [
            { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
            { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
          ],
          cursor: 'F0',
        }
      }
      return {
        orders: [
          { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
          { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
          { id: 'Z', status: 'pending', created_at: '2026-08-08T10:09:00Z' },
        ],
        cursor: 'F1',
      }
    },
    fetchChanges: async () => ({
      items: [],
      removed_ids: [],
      next_cursor: 'F0',
      has_more: false,
    }),
    filterOrders: (raw) => raw,
    playSound: () => {
      sounds5 += 1
    },
    setTimeoutFn: t5.setTimeoutFn,
    clearTimeoutFn: t5.clearTimeoutFn,
    now: t5.now,
    fullIntervalMs: 60000,
  })
  c5.start()
  await sleep(0)
  assert.equal(sounds5, 0)
  t5.advance(60000)
  await c5.sync('auto')
  assert.ok(full5 >= 2, 'periodic full should run')
  assert.equal(sounds5, 1, 'full repair alerts new pending')
  assert.ok(c5.isHighlighted('Z'))

  // visible / online / manual → full
  let full6 = 0
  const t6 = createFakeTimers()
  const c6 = createWorkbenchSyncCore({
    fetchFull: async () => {
      full6 += 1
      return { orders: [{ id: 'A', status: 'pending' }], cursor: 'V1' }
    },
    fetchChanges: async () => ({
      items: [],
      removed_ids: [],
      next_cursor: 'V1',
      has_more: false,
    }),
    filterOrders: (raw) => raw,
    setTimeoutFn: t6.setTimeoutFn,
    clearTimeoutFn: t6.clearTimeoutFn,
    now: t6.now,
  })
  c6.start()
  await sleep(0)
  assert.equal(full6, 1)
  c6.setVisible(false)
  c6.setVisible(true)
  await sleep(0)
  assert.equal(full6, 2)
  c6.setOnline(false)
  c6.setOnline(true)
  await sleep(0)
  assert.equal(full6, 3)
  await c6.syncNow()
  assert.equal(full6, 4)
}

// FG-08: overlap duplicate pending must not re-sound
{
  let sounds = 0
  let fullN = 0
  const t = createFakeTimers()
  const c = createWorkbenchSyncCore({
    fetchFull: async () => {
      fullN += 1
      return {
        orders: [{ id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' }],
        cursor: 'CUR',
      }
    },
    fetchChanges: async () => ({
      items: [{ id: 'C', status: 'pending', created_at: '2026-08-08T10:02:00Z' }],
      removed_ids: [],
      next_cursor: 'CUR2',
      has_more: false,
    }),
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
  await c.sync('delta')
  assert.equal(sounds, 1)
  await c.sync('delta')
  await c.sync('delta')
  assert.equal(sounds, 1, 'FG-08 overlap duplicate pending must not re-sound')
  void fullN
}

// FG-09: duplicate removed_id is idempotent
{
  const base = [
    { id: 'A', status: 'pending', created_at: '2026-08-08T10:00:00Z' },
    { id: 'B', status: 'pending', created_at: '2026-08-08T10:01:00Z' },
  ]
  const once = applyWorkbenchDelta(base, [], ['A'], (raw) => raw)
  const twice = applyWorkbenchDelta(once, [], ['A', 'A'], (raw) => raw)
  assert.deepEqual(
    twice.map((o) => o.id),
    ['B'],
  )
}

console.log('TEST-FE workbenchSync: passed')
