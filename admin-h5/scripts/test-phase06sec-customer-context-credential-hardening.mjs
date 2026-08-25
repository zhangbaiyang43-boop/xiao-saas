// Phase-06-SEC acceptance suite: CustomerList context identity must never embed the
// raw Bearer token, and logout must explicitly purge any saved context.
//
// This is a regression contract for a real finding: Phase-05C's currentContextIdentity()
// concatenated tenant_id + the raw access token and persisted that string into
// sessionStorage. The core assertion here is the one from the Phase-06 audit report --
// sessionStorage must never contain the literal token value in any form, and it must
// stay that way even as CustomerList.vue is touched again in the future.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const customerListSrc = fs.readFileSync(path.join(root, 'src/views/CustomerList.vue'), 'utf8').replace(/\r\n/g, '\n')
const authStoreSrc = fs.readFileSync(path.join(root, 'src/stores/auth.js'), 'utf8').replace(/\r\n/g, '\n')

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

function slice(src, startMarker, endMarker) {
  const rest = src.split(startMarker, 2)[1]
  if (rest == null) throw new Error(`marker not found: ${startMarker}`)
  return endMarker ? rest.split(endMarker, 1)[0] : rest
}

// ---------------------------------------------------------------------------
// Behavioral mirror of the hardened identity/save/clear logic.
// ---------------------------------------------------------------------------

const CONTEXT_KEY = 'admin_customer_list_context'

function makeStore() {
  const data = new Map()
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
  }
}

function currentContextIdentity(localStorageStore) {
  return localStorageStore.getItem('tenant_id') || ''
}

function saveListContext(sessionStorageStore, localStorageStore, keyword, page) {
  sessionStorageStore.setItem(CONTEXT_KEY, JSON.stringify({ identity: currentContextIdentity(localStorageStore), keyword, page }))
}

function clearAuthSessionCleanup(sessionStorageStore) {
  sessionStorageStore.removeItem(CONTEXT_KEY)
}

test('0. currentContextIdentity() no longer reads or embeds the raw token', () => {
  const fn = slice(customerListSrc, 'function currentContextIdentity() {', '\n}')
  assert.ok(!fn.includes("localStorage.getItem('token')"), 'currentContextIdentity must not read the raw Bearer token at all')
  assert.ok(fn.includes("localStorage.getItem('tenant_id')"), 'currentContextIdentity must still key on tenant_id for tenant isolation')
})

test('1. saveListContext() payload can never contain the literal token value', () => {
  const local = makeStore()
  local.setItem('tenant_id', 't1')
  local.setItem('token', 'super-secret-jwt-value')
  const session = makeStore()
  saveListContext(session, local, '张三', 2)
  const raw = session.getItem(CONTEXT_KEY)
  assert.ok(!raw.includes('super-secret-jwt-value'), 'the persisted sessionStorage payload must never contain the raw token as a substring')
})

test('2. clearAuth() in stores/auth.js explicitly purges the saved customer-list context', () => {
  const fn = slice(authStoreSrc, 'function clearAuth() {', '\n  }')
  assert.ok(fn.includes(`sessionStorage.removeItem('${CONTEXT_KEY}')`), 'clearAuth() must explicitly remove the customer-list context key, since identity no longer changes on same-tenant logout')
})

test('3. clearAuth() cleanup mirror actually removes a previously saved context', () => {
  const session = makeStore()
  const local = makeStore()
  local.setItem('tenant_id', 't1')
  saveListContext(session, local, '13800001111', 3)
  assert.ok(session.getItem(CONTEXT_KEY), 'precondition: a context was saved')
  clearAuthSessionCleanup(session)
  assert.equal(session.getItem(CONTEXT_KEY), null, 'after logout cleanup, no stale context may remain for the next login (even same tenant)')
})

test('4. Tenant isolation is still enforced without the token', () => {
  const session = makeStore()
  const localA = makeStore()
  localA.setItem('tenant_id', 'tenant-A')
  saveListContext(session, localA, '张三', 4)
  const savedRaw = session.getItem(CONTEXT_KEY)
  const saved = JSON.parse(savedRaw)
  const localB = makeStore()
  localB.setItem('tenant_id', 'tenant-B')
  assert.notEqual(saved.identity, currentContextIdentity(localB), 'tenant A\'s saved identity must not match tenant B\'s current identity')
})

test('5. No other place in CustomerList.vue reads the token for any storage-bound purpose', () => {
  assert.ok(!customerListSrc.includes("localStorage.getItem('token')"), 'CustomerList.vue must not read the raw token anywhere once the identity no longer needs it')
})

if (failures.length) {
  console.error(`Phase-06-SEC RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-06-SEC customer context credential hardening: passed')
