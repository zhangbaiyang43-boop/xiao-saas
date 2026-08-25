// Phase-05C acceptance suite: CustomerList work-context preservation across a
// List -> Detail -> back round trip.
//
// No Vue render / Vue Router test framework exists in this repo, so this combines
// static source assertions on the real file with a behavioral mirror of the real
// sessionStorage save/consume/restore logic (copied from the source, pinned against
// it verbatim in test 0) run against an in-memory fake sessionStorage/localStorage --
// proving the actual state-machine behavior (identity matching, consume-once,
// capped restore page), not just that certain strings appear in the file.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = fs.readFileSync(path.join(root, 'src/views/CustomerList.vue'), 'utf8').replace(/\r\n/g, '\n')

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
// Behavioral mirror of the real save/consume/restore logic, using a fake
// key-value store standing in for sessionStorage/localStorage.
// ---------------------------------------------------------------------------

const PAGE_SIZE = 30
const RESTORE_PAGE_SIZE_CAP = 200
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

function consumeSavedListContext(sessionStorageStore, localStorageStore) {
  const raw = sessionStorageStore.getItem(CONTEXT_KEY)
  sessionStorageStore.removeItem(CONTEXT_KEY)
  if (!raw) return null
  let saved
  try { saved = JSON.parse(raw) } catch { return null }
  if (!saved || saved.identity !== currentContextIdentity(localStorageStore)) return null
  return saved
}

function cappedRestorePage(savedPage) {
  return Math.max(1, Math.min(Number(savedPage) || 1, Math.floor(RESTORE_PAGE_SIZE_CAP / PAGE_SIZE)))
}

test('0. The mirror above matches the real save/consume/identity logic verbatim', () => {
  assert.ok(src.includes("function currentContextIdentity() {\n  return localStorage.getItem('tenant_id') || ''\n}"), 'currentContextIdentity must match the mirror (Phase-06-SEC: tenant_id only, no token)')
  assert.ok(src.includes('identity: currentContextIdentity(),\n      keyword: keyword.value,\n      page: page.value,'), 'saveListContext payload shape must match the mirror')
  assert.ok(src.includes('if (!saved || saved.identity !== currentContextIdentity()) return null'), 'consumeSavedListContext must reject any identity mismatch, matching the mirror')
  assert.ok(src.includes('Math.floor(RESTORE_PAGE_SIZE_CAP / PAGE_SIZE)'), 'the page cap formula must match the mirror')
  assert.ok(src.includes("const RESTORE_PAGE_SIZE_CAP = 200"), 'the cap constant must match the mirror (200, saas-base PAGE_MAX_LIMIT)')
})

// ---------------------------------------------------------------------------
// TEST 1-3: keyword/page/filters preserved across the round trip.
// ---------------------------------------------------------------------------

test('1. A keyword typed before opening a detail is restored on return', () => {
  const session = makeStore()
  const local = makeStore()
  local.setItem('tenant_id', 't1'); local.setItem('token', 'tok1')
  saveListContext(session, local, '王', 1)
  const saved = consumeSavedListContext(session, local)
  assert.equal(saved.keyword, '王')
})

test('2. A page depth beyond 1 is restored on return', () => {
  const session = makeStore()
  const local = makeStore()
  local.setItem('tenant_id', 't1'); local.setItem('token', 'tok1')
  saveListContext(session, local, '', 3)
  const saved = consumeSavedListContext(session, local)
  assert.equal(saved.page, 3)
  assert.equal(cappedRestorePage(saved.page), 3, 'a page within the cap must be restored exactly')
})

test('3. No real filter exists on CustomerList -- NOT_APPLICABLE, confirmed by source inspection', () => {
  const template = slice('<template>', '<script setup>')
  assert.ok(!/filters?\.value/.test(src), 'no filters ref/state exists to preserve')
  assert.ok(!template.includes('a-select') || !template.toLowerCase().includes('filter'), 'no filter control exists in the template beyond the keyword search box')
})

// ---------------------------------------------------------------------------
// TEST 4: restored context still drives a REAL backend request.
// ---------------------------------------------------------------------------

test('4. Restoring never reuses a stale in-memory array -- it always re-requests the real backend', () => {
  const restoreListContextFn = slice('async function restoreListContext(saved) {', '\n}')
  assert.ok(restoreListContextFn.includes('await loadCustomers('), 'restoreListContext must call loadCustomers, which issues a real getCustomers() request -- it must not directly assign customers.value from a saved snapshot')
  assert.ok(!src.includes('customers.value = saved'), 'no code path may assign customers.value directly from saved/restored state')
  const loadCustomersFn = slice('async function loadCustomers({', '\n\n// 从详情返回时调用')
  assert.ok(loadCustomersFn.includes('const res = await getCustomers(params)'), 'the restore path shares the exact same real API call as every other load')
})

// ---------------------------------------------------------------------------
// TEST 5: tenant isolation.
// ---------------------------------------------------------------------------

test('5. Tenant A\'s saved context can never be restored under Tenant B\'s identity', () => {
  const session = makeStore()
  const localA = makeStore()
  localA.setItem('tenant_id', 'tenant-A'); localA.setItem('token', 'tokA')
  saveListContext(session, localA, '张三', 4)

  // Same tab (same sessionStorage instance), but the identity now reads as tenant B --
  // e.g. after a re-login that rotated tenant_id/token.
  const localB = makeStore()
  localB.setItem('tenant_id', 'tenant-B'); localB.setItem('token', 'tokB')
  const saved = consumeSavedListContext(session, localB)
  assert.equal(saved, null, 'a context saved under tenant A must not be handed back under tenant B\'s identity')
  assert.equal(session.getItem(CONTEXT_KEY), null, 'the mismatched entry must still be consumed/removed, not left sitting for a later accidental match')
})

// ---------------------------------------------------------------------------
// TEST 6: logout / session change.
// ---------------------------------------------------------------------------

test('6. Same-tenant token rotation alone no longer invalidates by identity mismatch -- logout invalidation is now an explicit purge (Phase-06-SEC)', () => {
  // Phase-06-SEC removed the raw token from currentContextIdentity() (it was being
  // persisted into sessionStorage as a second plaintext copy of the Bearer credential --
  // see ADMIN_FRONTEND_SYSTEM_PHASE06_NEXT_PRIORITY_AUDIT.md). Identity is now tenant_id
  // only, so a token rotation under the SAME tenant_id no longer changes the identity by
  // itself. Logout/re-login invalidation is instead handled by an explicit
  // sessionStorage.removeItem('admin_customer_list_context') inside stores/auth.js's
  // clearAuth() (asserted directly against that file in
  // test-phase06sec-customer-context-credential-hardening.mjs), which runs on every real
  // logout path (More.vue, the three workbenches). This test documents the new contract
  // so a future change can't silently reintroduce token-based identity without noticing
  // this assertion flip.
  const session = makeStore()
  const local = makeStore()
  local.setItem('tenant_id', 't1'); local.setItem('token', 'old-token')
  saveListContext(session, local, '13800001111', 2)

  local.setItem('token', 'new-token-after-relogin')
  const saved = consumeSavedListContext(session, local)
  assert.notEqual(saved, null, 'identity no longer includes the token, so a same-tenant token rotation alone must NOT invalidate the saved context by itself')
  assert.equal(saved.keyword, '13800001111', 'the context that survives token rotation is exactly the one saved before it')
})

// ---------------------------------------------------------------------------
// TEST 7: Phase-03D error contract preserved.
// ---------------------------------------------------------------------------

test('7. A failure after returning from detail still follows the Phase-03D Error contract, not a fake success', () => {
  const loadCustomersFn = slice('async function loadCustomers({', '\n\n// 从详情返回时调用')
  assert.ok(loadCustomersFn.includes("if (res.code !== 200) throw new Error(res.msg || '会员加载失败')"), 'business failures must still be rejected on the restore path -- it goes through the same loadCustomers()')
  assert.ok(loadCustomersFn.includes('loadError.value = true'), 'a failure during restore must still set loadError, not silently show an empty/stale list as if it were fresh')
})

// ---------------------------------------------------------------------------
// TEST 8: detail-side mutation freshness.
// ---------------------------------------------------------------------------

test('8. Returning after a detail-side status change always re-fetches -- restore is never a frozen snapshot', () => {
  // Already covered structurally by test 4 (restore always calls the real API), but
  // pinned again here specifically against the mutation scenario: CustomerDetail.vue
  // can flip status via disableCustomer/restore (updateCustomerStatus), and the list
  // must reflect that on return, not the pre-detail-visit value.
  assert.ok(!src.includes('sessionStorage.setItem(CUSTOMER_LIST_CONTEXT_KEY, JSON.stringify({\n      identity: currentContextIdentity(),\n      keyword: keyword.value,\n      page: page.value,\n      customers'), 'the saved context payload must never include the customer rows themselves, only keyword/page -- confirms detail-side mutations cannot be masked by a stale cached row')
})

// ---------------------------------------------------------------------------
// TEST 9: a normal fresh entry inherits nothing.
// ---------------------------------------------------------------------------

test('9. A normal first-time entry (no prior detail visit) starts with an empty, non-inherited context', () => {
  const session = makeStore()
  const local = makeStore()
  local.setItem('tenant_id', 't1'); local.setItem('token', 'tok1')
  // Nothing was ever saved -- this is a fresh tab / fresh navigation from Dashboard.
  const saved = consumeSavedListContext(session, local)
  assert.equal(saved, null, 'consuming with nothing saved must return null, so onMounted falls through to the normal loadCustomers() path')
  const mountedBlock = slice('onMounted(() => {', '})')
  assert.ok(mountedBlock.includes('if (saved) restoreListContext(saved)') && mountedBlock.includes('else loadCustomers()'), 'onMounted must only restore when a saved context is actually present, otherwise falling back to the unchanged normal load')
})

// ---------------------------------------------------------------------------
// Architecture / scope checks.
// ---------------------------------------------------------------------------

test('No global keep-alive, no route query for keyword, no new large state dependency', () => {
  const routerSrc = fs.readFileSync(path.join(root, 'src/router/index.js'), 'utf8')
  const layoutSrc = fs.readFileSync(path.join(root, 'src/views/Layout.vue'), 'utf8')
  assert.ok(!/keep-alive|KeepAlive/.test(routerSrc), 'router/index.js must not introduce keep-alive')
  assert.ok(!/keep-alive|KeepAlive/.test(layoutSrc), 'Layout.vue (the shared router-view for every page) must remain untouched -- no keep-alive added')
  assert.ok(!src.includes('route.query.keyword') && !src.includes("query: { keyword"), 'keyword must never be placed in the route query (PII risk: phone numbers/names in URL history, logs, referrers, screenshots)')
  assert.ok(!src.includes("import { defineStore }") && !src.includes('Pinia'), 'no new Pinia store or large state dependency introduced for this -- state lives in sessionStorage, scoped to this one file')
})

if (failures.length) {
  console.error(`Phase-05C RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-05C customer context preservation: passed')
