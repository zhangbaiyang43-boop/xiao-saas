// Phase-05B acceptance suite: MenuManage dish-name search.
//
// No Vue render framework exists in this repo, so this combines static source
// assertions on the real file with a behavioral mirror of the real
// filteredCategories/dishesByCategory logic (copied verbatim from the source, with a
// source-text assertion pinning that the mirror actually matches what's shipped) --
// not just checking that the string "searchKeyword" appears somewhere.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
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

// ---------------------------------------------------------------------------
// Behavioral mirror of the real MenuManage.vue logic. Test 0 pins that this
// mirror's source strings actually exist verbatim in the real file, so the
// behavioral assertions below are proving something about the shipped code,
// not an idealized reimplementation.
// ---------------------------------------------------------------------------

function categoriesOf(allDishes) {
  const raw = []
  for (const d of allDishes) if (d.category && !raw.includes(d.category)) raw.push(d.category)
  return raw
}

function dishesByCategory(allDishes, keyword, cat) {
  const base = allDishes.filter((d) => d.category === cat)
  const q = keyword.trim().toLowerCase()
  return q ? base.filter((d) => (d.name || '').toLowerCase().includes(q)) : base
}

function filteredCategories(allDishes, keyword, activeCategory) {
  const q = keyword.trim().toLowerCase()
  const categories = categoriesOf(allDishes)
  if (q) return categories.filter((cat) => dishesByCategory(allDishes, keyword, cat).length > 0)
  return activeCategory ? [activeCategory] : categories
}

test('0. The mirror above matches the real dishesByCategory/filteredCategories source verbatim', () => {
  assert.ok(src.includes('function dishesByCategory(cat) {\n  const base = allDishes.value.filter(d => d.category === cat)\n  const q = searchKeyword.value.trim().toLowerCase()\n  return q ? base.filter(d => (d.name || \'\').toLowerCase().includes(q)) : base\n}'), 'dishesByCategory must match the mirrored implementation')
  assert.ok(src.includes('if (q) return categories.value.filter(cat => dishesByCategory(cat).length > 0)'), 'filteredCategories must filter categories.value down to those with at least one match when searching')
  assert.ok(src.includes('return activeCategory.value ? [activeCategory.value] : categories.value'), 'filteredCategories must fall back to the untouched activeCategory logic when not searching')
})

// ---------------------------------------------------------------------------
// TEST 1-3, 6-7: real filtering behavior.
// ---------------------------------------------------------------------------

const dishes = [
  { id: 1, name: '宫保鸡丁', category: '热销推荐' },
  { id: 2, name: '鱼香肉丝', category: '热销推荐' },
  { id: 3, name: '清炒时蔬', category: '素菜' },
  { id: 4, name: '可乐鸡翅', category: '招牌菜' },
]

test('1. The main dish list supports a real name search, wired to its own state -- distinct from the library-import search', () => {
  const template = slice('<template>', '<script setup>')
  assert.ok(template.includes('<a-input-search v-model:value="searchKeyword"'), 'a real search input bound to searchKeyword must exist in the main list template')
  const mainSearchIdx = template.indexOf('<a-input-search v-model:value="searchKeyword"')
  const dishListIdx = template.indexOf('<!-- 菜品列表 -->')
  const libraryDrawerIdx = template.indexOf("从菜品库导入")
  assert.ok(mainSearchIdx !== -1 && dishListIdx !== -1 && mainSearchIdx < dishListIdx, 'the main search box must sit before the dish list it filters, not after')
  assert.ok(libraryDrawerIdx === -1 || mainSearchIdx < libraryDrawerIdx, 'the main search box must be part of the primary list view, positioned before the separate library-import drawer markup')
  // searchKeyword and libraryKeyword must be two distinct refs -- confirms this is
  // not accidentally reusing/aliasing the library search's own keyword state.
  assert.ok(src.includes('const searchKeyword = ref(') && src.includes('const libraryKeyword = ref('), 'searchKeyword (main list) and libraryKeyword (library import) must be two separate, independent refs')
})

test('2. Matching a keyword only shows dishes whose real name contains it', () => {
  const result = filteredCategories(dishes, '鸡', '')
  // '宫保鸡丁' (热销推荐) and '可乐鸡翅' (招牌菜) match '鸡'; '鱼香肉丝' and '清炒时蔬' do not.
  assert.deepEqual(result.sort(), ['招牌菜', '热销推荐'].sort())
  assert.deepEqual(dishesByCategory(dishes, '鸡', '热销推荐').map((d) => d.id), [1])
  assert.deepEqual(dishesByCategory(dishes, '鸡', '招牌菜').map((d) => d.id), [4])
  assert.deepEqual(dishesByCategory(dishes, '鸡', '素菜'), [], '素菜 has no match for 鸡 and must return nothing')
})

test('3. Clearing the keyword restores the normal, unfiltered category view', () => {
  const withKeyword = filteredCategories(dishes, '鸡', '')
  const cleared = filteredCategories(dishes, '', '')
  assert.notDeepEqual(withKeyword.sort(), cleared.sort())
  assert.deepEqual(cleared.sort(), categoriesOf(dishes).sort(), 'clearing the keyword must return to the full, real category list')
  assert.deepEqual(dishesByCategory(dishes, '', '热销推荐').map((d) => d.id), [1, 2], 'clearing the keyword must restore the full dish list for a category')
})

test('6. Search ignores the active category (OPTION B) -- a real dish in another category is still found', () => {
  // Frozen contract: the owner is on the "素菜" tab but searches for a dish that
  // actually lives in "招牌菜". It must still be found, not reported as absent.
  const result = filteredCategories(dishes, '可乐', '素菜')
  assert.deepEqual(result, ['招牌菜'], 'a search match outside the currently active category tab must still surface -- must not silently scope to activeCategory')
})

test('7. Search never mutates the underlying allDishes array', () => {
  const before = JSON.parse(JSON.stringify(dishes))
  filteredCategories(dishes, '鸡', '')
  dishesByCategory(dishes, '鸡', '热销推荐')
  assert.deepEqual(dishes, before, 'filtering must not add, remove, or modify any dish in the real data source')
  assert.ok(!src.includes('const displayedDishes = ref'), 'search must not create a second, independently-tracked dish array -- filtering must stay derived (computed/function), not a copied ref')
})

// ---------------------------------------------------------------------------
// TEST 4-5: state-contract interaction with Phase-03C truthfulness.
// ---------------------------------------------------------------------------

test('4. A real search-no-result state is distinct from the true-empty-menu state', () => {
  const template = slice('<template>', '<script setup>')
  const trueEmptyIdx = template.indexOf('v-else-if="allDishes.length === 0"')
  const searchNoResultIdx = template.indexOf('v-else-if="searchKeyword.trim() && filteredCategories.length === 0"')
  assert.ok(trueEmptyIdx !== -1 && searchNoResultIdx !== -1, 'both a true-empty-menu branch and a distinct search-no-result branch must exist')
  assert.ok(trueEmptyIdx < searchNoResultIdx, 'the true-empty-menu check must be evaluated first (it is the stronger claim: there are zero dishes at all)')
  const searchNoResultBlock = slice('v-else-if="searchKeyword.trim() && filteredCategories.length === 0"', '</div>')
  assert.ok(searchNoResultBlock.includes('没有找到匹配'), 'search-no-result copy must say no match was found, not reuse the "还没有菜品" copy')
  assert.ok(!searchNoResultBlock.includes('添加第一道菜'), 'search-no-result must not invite creating a new dish -- that copy belongs only to the true-empty-menu state')
})

test('5. A load failure still renders Phase-03C\'s Error state and is not masked by the new search-no-result branch', () => {
  const template = slice('<template>', '<script setup>')
  const loadErrorEmptyIdx = template.indexOf('v-if="loadError && allDishes.length === 0"')
  const searchNoResultIdx = template.indexOf('v-else-if="searchKeyword.trim() && filteredCategories.length === 0"')
  assert.ok(loadErrorEmptyIdx !== -1 && searchNoResultIdx !== -1 && loadErrorEmptyIdx < searchNoResultIdx, 'the load-error branch (from Phase-03C) must still be evaluated before the new search-no-result branch, so a failure is never reinterpreted as "no search match"')
  // The search input itself must not render at all when there is no data to search
  // (allDishes.length === 0 covers both a genuine empty menu and a first-load failure).
  assert.ok(template.includes('<div v-if="allDishes.length > 0" class="section-block animate-in" style="padding:0 16px 8px">'), 'the search box must be gated on having real data to search, so it cannot appear to work during a first-load failure with no data')
})

if (failures.length) {
  console.error(`Phase-05B RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-05B menu high-frequency efficiency: passed')
