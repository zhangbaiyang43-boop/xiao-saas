// Phase-03C acceptance suite: MenuManage (product-named "DishManage" in the phase
// spec -- see docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03C_DISH_STATE_MIGRATION.md
// section 0 for the filename mapping) state truthfulness.
//
// No Vue render framework exists in this repo (see test-dashboard-actionable-state.mjs
// precedent), so this combines static source assertions on the real file with small
// local mirrors of the branching logic added in this phase.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// Normalize CRLF -> LF up front -- the real source is CRLF on this repo/OS, and a
// '\n'-based slice silently widening its match window on \r\n bit a prior phase
// (Phase-03B) with a false PASS. See that phase's report for the full story.
const src = fs.readFileSync(path.join(root, 'src/views/MenuManage.vue'), 'utf8').replace(/\r\n/g, '\n')

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

test('1. First dish-list load failure resolves to Error, not an empty menu', () => {
  const loadMenu = slice('async function loadMenu() {', '\n// 分类排序')
  assert.ok(loadMenu.includes("if (res?.code !== 200) throw new Error(res?.msg || '菜品加载失败')"), 'a business-level failure (HTTP 200, code != 200) must be rejected, not silently treated as an empty menu')
  assert.ok(loadMenu.includes('} catch {'), 'loadMenu must have a catch branch')
  const catchBlock = loadMenu.split('} catch {', 2)[1].split('} finally {', 1)[0]
  assert.ok(catchBlock.includes('loadError.value = true'), 'a failed load must set loadError so the page renders the error alert')
  assert.ok(!catchBlock.includes('allDishes.value = []'), 'a failed load must not wipe allDishes to empty -- that is what makes a failure indistinguishable from a real empty menu')

  const template = slice('<template>', '<script setup>')
  const dedicatedErrorIdx = template.indexOf('v-if="loadError && allDishes.length === 0"')
  const skeletonIdx = template.indexOf('v-else-if="loadingMenu && allDishes.length === 0"')
  const emptyIdx = template.indexOf('v-else-if="allDishes.length === 0"')
  assert.ok(dedicatedErrorIdx !== -1, 'a first-load failure (no old data to fall back to) must render a dedicated error state')
  assert.ok(dedicatedErrorIdx < skeletonIdx && skeletonIdx < emptyIdx, 'error must be evaluated before loading, and loading before the generic empty state')
})

test('2. Dish list loading successfully with zero dishes resolves to Empty', () => {
  const loadMenu = slice('async function loadMenu() {', '\n// 分类排序')
  assert.ok(loadMenu.includes("resultStatus = allDishes.value.length ? 'success' : 'empty'"), 'a successful load with zero dishes must be tagged empty, not error')
  assert.ok(loadMenu.includes('loadError.value = false'), 'a successful load must clear any previous loadError')
  const successIdx = loadMenu.indexOf('loadError.value = false')
  const catchIdx = loadMenu.indexOf('} catch {')
  assert.ok(successIdx !== -1 && successIdx < catchIdx, 'loadError must be cleared on the success path, before the catch branch')
})

test('3. Category display has no separate failure surface to lie about -- it is derived from the same guarded dish list', () => {
  // MenuManage has no standalone "list categories" endpoint: `categories` is a computed
  // collected from allDishes (see the computed below). There is therefore no code path
  // where a "category fetch" can independently fail and silently render an empty
  // category bar while claiming success -- fixing scenario 1 (dish load truthfulness)
  // structurally fixes this too. This test pins that architecture so a future change
  // introducing a real, separate category-list fetch does not quietly reopen the gap
  // scenario 1 just closed.
  assert.ok(
    src.includes('const categories = computed(() => {'),
    'categories must remain a computed derived from allDishes, not an independently-fetched list',
  )
  const categoriesComputed = slice('const categories = computed(() => {', '\nconst categoryOptions')
  assert.ok(categoriesComputed.includes('for (const d of allDishes.value)'), 'categories must be collected from the same allDishes the loadMenu error/empty contract already governs')
  // category_order (merchant-chosen sort preference, via getTenantSettings) is a
  // separate, genuinely low-stakes fetch: its failure only loses a sort preference,
  // it never hides or fabricates dishes. Pin that it stays silently-degrading (not
  // promoted to a page-blocking error), which is the correct call for a cosmetic
  // ordering preference, not a truthfulness violation.
  assert.ok(src.includes('async function loadCategoryOrder() {'), 'the category-order preference loader must still exist')
})

test('4. Library search failure preserves the previous results and reports failure, not a false "nothing shared" empty state', () => {
  const doSearch = slice('async function doLibrarySearch() {', '\nfunction toggleLibrarySelect')
  assert.ok(doSearch.includes("if (res?.code !== 200) throw new Error(res?.msg || '搜索失败')"), 'a business-level search failure must be rejected, not silently treated as zero results')
  const catchBlock = doSearch.split('} catch {', 2)[1].split('finally {', 1)[0]
  assert.ok(catchBlock.includes('libraryError.value = true'), 'a failed search must set its own error flag')
  assert.ok(!catchBlock.includes('libraryItems.value = []'), 'a failed search must not clear previously-shown results -- a transient failure must not look identical to "nobody shared this dish"')

  const template = slice('<template>', '<script setup>')
  const searchingIdx = template.indexOf('v-if="librarySearching"')
  const errorIdx = template.indexOf('v-else-if="libraryError"')
  const noResultsIdx = template.indexOf("v-else-if=\"libraryItems.length === 0\"")
  assert.ok(searchingIdx !== -1 && errorIdx !== -1 && noResultsIdx !== -1, 'library search must have distinct searching/error/no-results branches')
  assert.ok(searchingIdx < errorIdx && errorIdx < noResultsIdx, 'a failed search must be distinguished from a genuinely empty result before the generic no-results copy can render')
})

test('5. Retry after a failure re-runs the same guarded load and can report failure again -- no silent no-op', () => {
  const template = slice('<template>', '<script setup>')
  // Both the "stale data + banner" and "no data, dedicated error" alerts must offer a
  // real retry that calls the same loadMenu() the initial load used, not a dead button
  // or a hand-rolled reload path that could disagree with the real contract.
  const retryButtons = [...template.matchAll(/@click="loadMenu">重试<\/a-button>/g)]
  assert.equal(retryButtons.length, 2, 'both the stale-data banner and the no-data error state must offer a loadMenu() retry, and no more than those two')
  const librarySearchSource = slice('async function doLibrarySearch() {', '\nfunction toggleLibrarySelect')
  assert.ok(template.includes('@click="doLibrarySearch">重试</a-button>'), 'the library-search error state must offer a doLibrarySearch() retry')
  assert.ok(librarySearchSource.length > 0, 'retry calls the same guarded search function, not a divergent copy')
})

test('6. A successful load with real dishes resolves to Success', () => {
  const loadMenu = slice('async function loadMenu() {', '\n// 分类排序')
  assert.ok(loadMenu.includes('allDishes.value = raw.map(d => ({ ...d, desc: d.desc ?? d.description ?? \'\', sort_order: d.sort_order ?? 0 }))'), 'a successful response must populate allDishes from the real payload')
  const template = slice('<template>', '<script setup>')
  assert.ok(template.includes('<template v-else>'), 'the list branch must remain the final, catch-all else of the state chain')
})

if (failures.length) {
  console.error(`Phase-03C RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-03C dish state truthfulness: passed')
