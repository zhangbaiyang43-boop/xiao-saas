// Phase-03D acceptance suite: CustomerList (product-named "MemberManage" in the phase
// spec -- see docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03D_MEMBER_DATA_MIGRATION.md
// section 0 for the filename mapping) data accessibility and state truthfulness.
//
// No Vue render framework exists in this repo (see test-dashboard-actionable-state.mjs
// precedent), so this combines static source assertions on the real file with small
// local mirrors of the branching logic added in this phase.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// Normalize CRLF -> LF up front (Phase-03B bit itself on this once already).
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

test('1. First page reads a real backend total, not array.length pretending to be the count', () => {
  const loadCustomers = slice('async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {', '\n\n// 从详情返回时调用')
  assert.ok(
    loadCustomers.includes('total.value = Number(data?.total ?? customers.value.length)'),
    'total must come from the response payload\'s real total field, only falling back to length when the field is genuinely absent',
  )
  assert.ok(!src.includes('customers.value.length') || !src.includes('const total = computed'), 'total must not be a computed derived purely from customers.value.length -- that would just relabel the same client-side count')
  assert.ok(src.includes('const total = ref(0)'), 'total must be its own piece of state fed by the backend response, not derived from the loaded rows')
})

test('2. Requesting more members triggers a real second-page API call, not revealing more of an already-fetched array', () => {
  assert.ok(!src.includes('page_size: 100'), 'the old fixed page_size:100 single-shot fetch must be gone')
  assert.ok(!src.includes('pageSize.value += 30'), 'the old client-side reveal-more-of-the-same-100 mechanism must be gone')
  assert.ok(!src.includes('const visibleCustomers = computed'), 'there must no longer be a client-side slice standing in for pagination')
  const loadMore = slice('async function loadMore() {', '\nfunction goToDetail')
  assert.ok(loadMore.includes('const nextPage = page.value + 1'), 'loadMore must advance to a genuinely new page number')
  assert.ok(loadMore.includes('params = { page: nextPage, page_size: PAGE_SIZE }'), 'loadMore must send the real next page number to the backend, not repeat page 1')
  assert.ok(loadMore.includes('const res = await getCustomers(params)'), 'loadMore must issue its own real API call')
  assert.ok(loadMore.includes('page.value = nextPage'), 'page must only advance after a confirmed successful fetch, so a retry after failure re-requests the same page rather than skipping it')
})

test('3. Changing the search keyword re-queries the backend, not a client-side filter over the first page', () => {
  const loadCustomers = slice('async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {', '\n\n// 从详情返回时调用')
  assert.ok(loadCustomers.includes('if (keyword.value) params.search = keyword.value'), 'the current keyword must be sent to the backend as a real search param')
  assert.ok(!src.includes('.filter(c => c.name.includes(keyword'), 'search must not be simulated with an in-memory array filter')
  const loadMore = slice('async function loadMore() {', '\nfunction goToDetail')
  assert.ok(loadMore.includes('if (keyword.value) params.search = keyword.value'), 'pagination must carry the same active keyword forward, not silently drop it on page 2+')
})

test('4. A request failure resolves to Error, never a fabricated empty member list', () => {
  const loadCustomers = slice('async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {', '\n\n// 从详情返回时调用')
  assert.ok(loadCustomers.includes("if (res.code !== 200) throw new Error(res.msg || '会员加载失败')"), 'a business-level failure must be rejected through the same path as a network failure -- no separate branch that forgets to set loadError')
  const catchBlock = loadCustomers.split('} catch (e) {', 2)[1].split('} finally {', 1)[0]
  assert.ok(catchBlock.includes('loadError.value = true'), 'any failure (business or network) must set loadError')
  assert.ok(!catchBlock.includes('customers.value = []'), 'a failure must not wipe the member list to empty')

  const template = slice('<template>', '<script setup>')
  const dedicatedErrorIdx = template.indexOf('v-else-if="loadError && (customers.length === 0 || loadedKeyword !== keyword)"')
  const skeletonIdx = template.indexOf('v-if="loading && customers.length === 0"')
  const emptyIdx = template.indexOf('v-else-if="customers.length === 0"')
  assert.ok(dedicatedErrorIdx !== -1 && skeletonIdx !== -1 && emptyIdx !== -1, 'the state chain must have distinct loading/error/empty branches')
  assert.ok(skeletonIdx < dedicatedErrorIdx && dedicatedErrorIdx < emptyIdx, 'loading must be checked first, then error, before the generic empty state can ever render')
})

test('5. A confirmed real zero-result response resolves to Empty', () => {
  const loadCustomers = slice('async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {', '\n\n// 从详情返回时调用')
  assert.ok(loadCustomers.includes("resultStatus = customers.value.length ? 'success' : 'empty'"), 'a successful response with zero rows must be tagged empty, not error')
  assert.ok(loadCustomers.includes('loadError.value = false'), 'a successful response must explicitly clear loadError, including when it returns zero rows')
  const successIdx = loadCustomers.indexOf('loadError.value = false')
  const catchIdx = loadCustomers.indexOf('} catch (e) {')
  assert.ok(successIdx !== -1 && successIdx < catchIdx, 'loadError must be cleared on the success path, ahead of the catch branch')
})

test('6. A refresh failure on an already-loaded, same-keyword list preserves the existing members', () => {
  const template = slice('<template>', '<script setup>')
  assert.ok(
    template.includes('v-if="loadError && customers.length > 0 && loadedKeyword === keyword"'),
    'a same-keyword refresh failure with existing data must render a persistent stale-data banner, not silence or data loss',
  )
  assert.ok(template.includes('会员同步失败，当前显示的是上次数据'), 'the banner must say the shown data may be stale, not claim it is fresh')
  const loadCustomers = slice('async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {', '\n\n// 从详情返回时调用')
  assert.ok(!loadCustomers.includes('customers.value = []'), 'loadCustomers must never clear customers.value on any path, including failure')
  // A search to a genuinely different keyword that then fails must NOT show the old
  // keyword's results relabeled as current -- pinned separately, this is the
  // complementary branch to the banner above (see test 4's dedicated-error assertions).
  assert.ok(template.includes('loadedKeyword !== keyword'), 'a keyword-mismatched stale result must not be presented as the current query\'s data')
})

if (failures.length) {
  console.error(`Phase-03D RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-03D member data accessibility: passed')
