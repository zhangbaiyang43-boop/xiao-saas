import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const { createWorkbenchSyncCore, ownerActionableIdsFromOrders } = await import(
  pathToFileURL(path.join(root, 'src/composables/workbenchSyncCore.js')).href
)

const server = {
  orders: new Map(),
  changes: [],
  commit(order, commitAt) {
    const row = { ...order, id: String(order.id), commitAt }
    this.orders.set(row.id, row)
    this.changes.push({ seq: this.changes.length + 1, commitAt, order: row })
  },
}

for (let i = 1; i <= 5; i += 1) {
  server.orders.set(String(i), {
    id: String(i),
    status: 'pending_payment',
    payment_status: 'unpaid',
    payment_mode: 'prepay',
    commitAt: -100,
  })
}

function percentile(values, ratio) {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * ratio) - 1)] || 0
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve))
}

function createLogicalClient(name) {
  let now = 0
  let sounds = 0
  const appliedAt = new Map()
  const statusAppliedAt = new Map()
  const sync = createWorkbenchSyncCore({
    fetchFull: async () => ({
      orders: [...server.orders.values()].map((order) => ({ ...order })),
      cursor: String(server.changes.length),
    }),
    fetchChanges: async (cursor) => {
      const eligible = server.changes.filter(
        (change) => change.seq > Number(cursor || 0) && change.commitAt <= now,
      )
      const items = eligible.flatMap((change) => [{ ...change.order }, { ...change.order }])
      return {
        items,
        removed_ids: [],
        next_cursor: String(eligible.at(-1)?.seq || Number(cursor || 0)),
        has_more: false,
      }
    },
    filterOrders: (orders) => orders,
    alertIdsFromOrders: ownerActionableIdsFromOrders,
    playSound: () => { sounds += 1 },
    now: () => now,
    onChange: (state) => {
      for (const order of state.orders) {
        if (order.status === 'pending' && !appliedAt.has(order.id)) appliedAt.set(order.id, now)
        const key = `${order.id}:${order.status}`
        if (!statusAppliedAt.has(key)) statusAppliedAt.set(key, now)
      }
    },
    setTimeoutFn: () => 1,
    clearTimeoutFn: () => {},
    getIdentity: () => `${name}:tenant-a:token-a`,
  })
  return {
    name,
    sync,
    appliedAt,
    statusAppliedAt,
    get sounds() { return sounds },
    setNow(value) { now = value },
  }
}

const clients = [createLogicalClient('device-a'), createLogicalClient('device-b')]
for (const client of clients) client.sync.start()
await flush()
assert.equal(clients[0].sounds, 0, 'initial snapshot must not alert')
assert.equal(clients[1].sounds, 0, 'initial snapshot must not alert')

const commitTimes = new Map()
for (let i = 1; i <= 20; i += 1) {
  const commitAt = 100 + (i - 1) * 200
  commitTimes.set(String(i), commitAt)
  if (i <= 5) {
    server.commit({
      ...server.orders.get(String(i)),
      status: 'pending',
      payment_status: 'paid',
    }, commitAt)
  } else if (i <= 10) {
    server.commit({ id: i, status: 'pending', payment_status: 'unpaid', payment_mode: 'postpay' }, commitAt)
  } else {
    server.commit({
      id: i,
      status: 'pending',
      payment_status: 'unpaid',
      payment_mode: 'table_account',
      dining_session_id: 'same-session',
    }, commitAt)
  }
}

for (const client of clients) {
  client.setNow(5050)
  await client.sync.sync('delta')
}

const visibilityLatencies = []
for (const client of clients) {
  const rows = client.sync.getState().orders
  assert.equal(rows.length, 20)
  assert.equal(new Set(rows.map((order) => order.id)).size, 20)
  assert.equal(client.sounds, 1, 'one batch must produce one sound')
  for (const [id, committedAt] of commitTimes) {
    assert.ok(client.appliedAt.has(id), `${client.name} missing ${id}`)
    visibilityLatencies.push(client.appliedAt.get(id) - committedAt)
  }
}

const statusCommitTimes = new Map()
for (let i = 1; i <= 20; i += 1) {
  const status = i <= 10 ? 'preparing' : (i <= 15 ? 'done' : 'rejected')
  const commitAt = 5200 + (i - 1) * 200
  statusCommitTimes.set(`${i}:${status}`, commitAt)
  server.commit({ ...server.orders.get(String(i)), status }, commitAt)
}

for (const client of clients) {
  client.setNow(10150)
  await client.sync.sync('delta')
}

const statusLatencies = []
for (const client of clients) {
  const actual = new Map(client.sync.getState().orders.map((order) => [order.id, order.status]))
  for (const order of server.orders.values()) assert.equal(actual.get(order.id), order.status)
  for (const [key, committedAt] of statusCommitTimes) {
    assert.ok(client.statusAppliedAt.has(key), `${client.name} missing status ${key}`)
    statusLatencies.push(client.statusAppliedAt.get(key) - committedAt)
  }
}

clients[1].sync.setVisible(false)
server.commit({ id: '21', status: 'pending', payment_mode: 'postpay' }, 10200)
server.commit({ id: '22', status: 'pending', payment_mode: 'postpay' }, 10300)
server.commit({ id: '23', status: 'pending', payment_mode: 'table_account' }, 10400)
server.commit({ ...server.orders.get('1'), status: 'done' }, 10500)
clients[1].setNow(130500)
clients[1].sync.setVisible(true)
await flush()
assert.equal(clients[1].sync.getState().orders.length, 23)
assert.equal(clients[1].sync.getState().orders.find((order) => order.id === '1').status, 'done')

const visibilityP50 = percentile(visibilityLatencies, 0.5)
const visibilityP95 = percentile(visibilityLatencies, 0.95)
const visibilityMax = Math.max(...visibilityLatencies)
const statusP50 = percentile(statusLatencies, 0.5)
const statusP95 = percentile(statusLatencies, 0.95)
const statusMax = Math.max(...statusLatencies)

assert.ok(visibilityP95 <= 5000)
assert.ok(statusP95 <= 5000)

console.log('ORDERS_CREATED=20')
console.log('ACTIONABLE_TRANSITIONS=20')
console.log('DEVICE_A_VISIBLE=20')
console.log('DEVICE_B_VISIBLE=20')
console.log('DEVICE_A_MISSING=0')
console.log('DEVICE_B_MISSING=0')
console.log('DUPLICATE_ROWS_A=0')
console.log('DUPLICATE_ROWS_B=0')
console.log('STATUS_MISMATCH_COUNT=0')
console.log(`VISIBILITY_P50_MS=${visibilityP50}`)
console.log(`VISIBILITY_P95_MS=${visibilityP95}`)
console.log(`VISIBILITY_MAX_MS=${visibilityMax}`)
console.log(`STATUS_SYNC_P50_MS=${statusP50}`)
console.log(`STATUS_SYNC_P95_MS=${statusP95}`)
console.log(`STATUS_SYNC_MAX_MS=${statusMax}`)
console.log('BACKGROUND_TWO_MINUTE_MISSING=0')

for (const client of clients) client.sync.stop()
