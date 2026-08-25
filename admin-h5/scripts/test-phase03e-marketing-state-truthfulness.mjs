// Phase-03E acceptance suite: Marketing / CouponCenter state truthfulness.
//
// PRODUCT_CONCEPT -> REAL_FILE mapping (see
// docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03E_MARKETING_STATE_MIGRATION.md section 0):
//   Marketing (automatic marketing status/intensity + manual coupons) -> CouponCenter.vue
//   Marketing effect / insight                                        -> MarketingEffectiveness.vue
//   Coupon issuance records                                            -> CouponRecords.vue
//
// CouponCenter.vue had real, confirmed defects (fixed in this phase) -- those tests were
// verified RED against the actual pre-fix source via `git stash` (see report section 6).
// MarketingEffectiveness.vue and CouponRecords.vue were already compliant on audit; their
// tests here are regression locks, not RED->GREEN fixes -- no code changed in those files.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
function readSrc(relPath) {
  return fs.readFileSync(path.join(root, relPath), 'utf8').replace(/\r\n/g, '\n')
}
const couponCenter = readSrc('src/views/CouponCenter.vue')
const marketingEffectiveness = readSrc('src/views/MarketingEffectiveness.vue')
const couponRecords = readSrc('src/views/CouponRecords.vue')

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
// CouponCenter.vue -- real defects, fixed in this phase.
// ---------------------------------------------------------------------------

test('1. A failed marketing-status fetch never renders as "自动运行中"', () => {
  const template = slice(couponCenter, '<template>', '<script setup>')
  assert.ok(
    template.includes('v-if="previewLoaded && !previewError" class="hero-badge"><span class="live-dot"></span>自动运行中'),
    'the running badge must be gated on a confirmed successful load, not shown unconditionally',
  )
  assert.ok(!template.match(/<div class="hero-badge"><span class="live-dot"><\/span>自动运行中<\/div>\s*<h1>/), 'the old unconditional hardcoded badge must be gone')
  const loadPreview = slice(couponCenter, 'async function loadPreview() {', '\nasync function loadTemplates')
  assert.ok(loadPreview.includes("if (res?.code !== 200) throw new Error(res?.msg || '营销状态加载失败')"), 'a business-level failure must be rejected, not silently accepted as success')
  assert.ok(loadPreview.includes('previewError.value = true'), 'a failure (business or network) must set previewError')
})

test('2. A successful marketing-status fetch renders the real backend state', () => {
  const loadPreview = slice(couponCenter, 'async function loadPreview() {', '\nasync function loadTemplates')
  assert.ok(loadPreview.includes('previewError.value = false'), 'a successful fetch must clear any previous error')
  assert.ok(loadPreview.includes('preview.value = res?.data?.data || res?.data || {}'), 'a successful fetch must populate preview from the real response payload')
  const template = slice(couponCenter, '<template>', '<script setup>')
  assert.ok(template.includes("opt.key === currentIntensity"), 'the selected intensity pill must reflect the real backend-reported current_intensity once confirmed')
})

test('3. A marketing-statistics fetch failure hides the numbers instead of showing a fabricated 0', () => {
  const template = slice(couponCenter, '<template>', '<script setup>')
  const statsIdx = template.indexOf('v-if="previewLoaded && !previewError" class="hero-stat-row"')
  const errorRowIdx = template.indexOf('v-else-if="previewError" class="hero-error-row"')
  assert.ok(statsIdx !== -1 && errorRowIdx !== -1, 'the stat numbers and the error row must be distinct, mutually exclusive branches')
  assert.ok(statsIdx < errorRowIdx, 'the stat-number branch must be checked (and excluded) before the error branch renders')
})

test('4. A real zero count (genuinely zero coupons issued) is still allowed to display as 0', () => {
  const template = slice(couponCenter, '<template>', '<script setup>')
  assert.ok(template.includes('{{ preview.issued_this_month ?? 0 }}'), 'issued_this_month must still render 0 when that is what a SUCCESSFUL response reports -- the fix must not hide real zeroes, only fabricated ones')
  const statsGate = template.slice(template.indexOf('v-if="previewLoaded && !previewError" class="hero-stat-row"'))
  assert.ok(statsGate.indexOf('preview.issued_this_month') < statsGate.indexOf('</div>\n      <div v-else-if'), 'the real-zero-capable number must only be reachable through the success-gated branch')
})

test('6. A business-level failure (HTTP 200, code != 200) cannot be mistaken for success anywhere on this page', () => {
  const loadPreview = slice(couponCenter, 'async function loadPreview() {', '\nasync function loadTemplates')
  const loadTemplates = slice(couponCenter, 'async function loadTemplates() {', '\n// ── 强度切换')
  const switchIntensity = slice(couponCenter, 'async function switchIntensity(key) {', '\n// ── 手动建券')
  const saveTemplate = slice(couponCenter, 'async function saveTemplate() {', '\n// ── 工具函数')
  assert.ok(loadPreview.includes('res?.code !== 200'), 'loadPreview must check the business code')
  assert.ok(loadTemplates.includes('res?.code !== 200'), 'loadTemplates must check the business code')
  assert.ok(switchIntensity.includes("if (res?.code !== 200)"), 'switchIntensity (an existing action) must already gate its success toast on the business code -- confirmed compliant, locked here')
  assert.ok(saveTemplate.includes("if (res?.code !== 200)"), 'saveTemplate (an existing action) must already gate its success toast on the business code -- confirmed compliant, locked here')
})

test('7. Existing preview/template data is not wiped by a subsequent failed reload', () => {
  const loadPreview = slice(couponCenter, 'async function loadPreview() {', '\nasync function loadTemplates')
  const loadTemplates = slice(couponCenter, 'async function loadTemplates() {', '\n// ── 强度切换')
  const previewCatch = loadPreview.split('} catch {', 2)[1].split('} finally {', 1)[0]
  const templatesCatch = loadTemplates.split('} catch {', 2)[1].split('} finally {', 1)[0]
  assert.ok(!previewCatch.includes('preview.value = {}') && !previewCatch.includes('preview.value ='), 'a failed preview reload must not clear or overwrite preview.value')
  assert.ok(!templatesCatch.includes('templates.value = []') && !templatesCatch.includes('templates.value ='), 'a failed templates reload must not clear the previously-shown coupon list')
})

test('8. Preview and templates fail independently -- one does not contaminate the other', () => {
  const loadPreview = slice(couponCenter, 'async function loadPreview() {', '\nasync function loadTemplates')
  const loadTemplates = slice(couponCenter, 'async function loadTemplates() {', '\n// ── 强度切换')
  assert.ok(!loadPreview.includes('templatesError'), 'loadPreview must not touch templatesError')
  assert.ok(!loadTemplates.includes('previewError'), 'loadTemplates must not touch previewError')
})

test('NO_REAL_UNKNOWN_SCENARIO check: the manual-coupon empty copy no longer asserts the automatic system is running', () => {
  const template = slice(couponCenter, '<template>', '<script setup>')
  assert.ok(!template.includes('还没有手动建券，系统自动券已在运行'), 'the manual-coupon empty state must not smuggle in an unverified claim about the automatic system\'s status')
  assert.ok(template.includes('还没有手动建券'), 'the manual-coupon empty state copy must still exist in some form')
})

// ---------------------------------------------------------------------------
// MarketingEffectiveness.vue -- already compliant on audit. Regression locks only.
// ---------------------------------------------------------------------------

test('MarketingEffectiveness: a business-level failure renders Error, never a fabricated empty/zero table', () => {
  const loadData = slice(marketingEffectiveness, 'async function loadData() {', '\nfunction switchWindow')
  assert.ok(loadData.includes("if (res?.code !== 200) throw new Error(res?.msg || '加载失败')"), 'business failures must be rejected')
  assert.ok(loadData.includes('hasError.value = true'), 'a failure must set hasError')
  const template = slice(marketingEffectiveness, '<template>', '<script setup>')
  const loadingIdx = template.indexOf('v-if="loading"')
  const errorIdx = template.indexOf('v-else-if="hasError"')
  const listIdx = template.indexOf('<template v-else>')
  assert.ok(loadingIdx !== -1 && errorIdx !== -1 && listIdx !== -1 && loadingIdx < errorIdx && errorIdx < listIdx, 'loading, then error, then the data tables must be mutually exclusive and correctly ordered')
})

test('MarketingEffectiveness: a real 0% redemption rate is distinguished from "no data yet"', () => {
  const formatRate = slice(marketingEffectiveness, 'const formatRate = (value) => {', '\n}')
  assert.ok(formatRate.includes('if (value === null || value === undefined) return \'暂无数据\''), 'a missing rate must say so explicitly, not render as 0%')
})

// ---------------------------------------------------------------------------
// CouponRecords.vue -- already compliant on the loading/error/empty/list contract and
// real pagination. Regression locks only.
// ---------------------------------------------------------------------------

test('CouponRecords: a business-level failure renders Error and does not fall through to the empty-records copy', () => {
  const loadRecords = slice(couponRecords, 'const loadRecords = async () => {', '\nconst handleSearch')
  assert.ok(loadRecords.includes("if (res.code !== 200) {"), 'business failures must be rejected')
  assert.ok(loadRecords.includes('hasError.value = true'), 'a failure must set hasError')
  const template = slice(couponRecords, '<template>', '<script setup>')
  const loadingIdx = template.indexOf('v-if="loading"')
  const errorIdx = template.indexOf('v-else-if="hasError"')
  const emptyIdx = template.indexOf('v-else-if="records.length === 0"')
  assert.ok(loadingIdx < errorIdx && errorIdx < emptyIdx, 'loading, then error, then the true-empty state must be mutually exclusive and correctly ordered')
})

test('CouponRecords: pagination total comes from the real backend field, not a client-side row count', () => {
  const loadRecords = slice(couponRecords, 'const loadRecords = async () => {', '\nconst handleSearch')
  assert.ok(loadRecords.includes('pagination.value.total = extractTotal(res.data)'), 'total must be read from the response payload')
  const extractTotal = slice(couponRecords, 'const extractTotal = (data) => {', '\n}')
  assert.ok(extractTotal.includes('data?.total ?? data?.count'), 'extractTotal must prefer the real backend total/count field over a derived row-length fallback')
})

if (failures.length) {
  console.error(`Phase-03E RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-03E marketing state truthfulness: passed')
