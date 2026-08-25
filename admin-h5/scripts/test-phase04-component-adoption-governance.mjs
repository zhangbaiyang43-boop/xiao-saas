// Phase-04 governance contract suite: page consistency and component adoption.
//
// This is not a state-truthfulness fix phase (see Phase-03A-E), so these tests pin
// governance facts established by the real import graph and the two Touch And Migrate
// points implemented in this phase, not business behavior.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const srcDir = path.join(root, 'src')

function readSrc(relPath) {
  return fs.readFileSync(path.join(root, relPath), 'utf8').replace(/\r\n/g, '\n')
}

function walk(dir, exts, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, exts, out)
    else if (exts.some((ext) => entry.name.endsWith(ext))) out.push(full)
  }
  return out
}

const allSourceFiles = walk(srcDir, ['.vue', '.js', '.ts'])
function countRealConsumers(componentFileName, importPathFragment) {
  let count = 0
  for (const file of allSourceFiles) {
    if (file.endsWith(`components/${componentFileName}`)) continue // the component's own file
    const text = fs.readFileSync(file, 'utf8')
    if (new RegExp(`^import\\s+\\w+\\s+from\\s+['"][^'"]*${importPathFragment}(\\.vue)?['"]`, 'm').test(text)) count += 1
  }
  return count
}

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

// ---------------------------------------------------------------------------
// PART_09 -- deleted components must have zero real references left anywhere.
// A future accidental re-import of a deleted file is a build break; this catches
// it in a test instead of a broken build.
// ---------------------------------------------------------------------------

test('Deleted dead components have no remaining imports anywhere in admin-h5', () => {
  const deletedNames = [
    'DataCard', 'ListState', 'NavBar', 'PaginationBar', 'RefreshList',
    'CustomCheckbox', 'CustomDatePicker', 'CustomRadio', 'CustomTable',
  ]
  for (const file of walk(srcDir, ['.vue', '.js', '.ts'])) {
    const text = fs.readFileSync(file, 'utf8')
    for (const name of deletedNames) {
      assert.ok(
        !new RegExp(`from ['"][^'"]*${name}(\\.vue)?['"]`).test(text),
        `${path.relative(root, file)} must not import the deleted ${name}`,
      )
    }
  }
})

test('The dead components/index.ts barrel is gone, not left as an empty re-export shim', () => {
  assert.ok(!fs.existsSync(path.join(srcDir, 'components/index.ts')), 'components/index.ts must be deleted, not kept as a compatibility shim -- it had zero consumers')
})

// ---------------------------------------------------------------------------
// PART_03/PART_05 -- certified L2 components must not silently lose consumers.
// These counts were verified by real import-graph inspection in this phase (not by
// name alone -- e.g. SubscriptionSettings.vue mentions AssistedOrderSheet/TabBar only
// in comments, which this test's import-statement regex correctly excludes).
// ---------------------------------------------------------------------------

test('Certified Level-2 components keep at least their currently-evidenced real consumer count', () => {
  const minimums = {
    'PageHeader.vue': 20, // 19 pre-existing + CouponCenter.vue added this phase
    'WorkbenchSyncBar.vue': 3,
    'AssistedOrderSheet.vue': 2,
    'PickupNoPicker.vue': 2,
    'TabBar.vue': 1,
  }
  for (const [file, min] of Object.entries(minimums)) {
    const name = file.replace('.vue', '')
    const count = countRealConsumers(file, name)
    assert.ok(count >= min, `${file} must have at least ${min} real (import-statement) consumers, found ${count}`)
  }
})

// ---------------------------------------------------------------------------
// PART_10 implementation A: CouponCenter.vue PageHeader adoption + Constitution
// §2.3 compliance (no raw <button> duplicating a framework component).
// ---------------------------------------------------------------------------

test('CouponCenter.vue now uses PageHeader, matching its two sibling marketing pages', () => {
  const couponCenter = readSrc('src/views/CouponCenter.vue')
  assert.ok(couponCenter.includes("import PageHeader from '../components/PageHeader.vue'"), 'CouponCenter.vue must import the shared PageHeader')
  assert.ok(couponCenter.includes('<PageHeader title="智能营销" />'), 'CouponCenter.vue must render PageHeader with a real title')
  const pageHeaderIdx = couponCenter.indexOf('<PageHeader')
  const heroIdx = couponCenter.indexOf('<section class="hero-card')
  assert.ok(pageHeaderIdx !== -1 && heroIdx !== -1 && pageHeaderIdx < heroIdx, 'PageHeader must render before the hero card, not after')
})

test('CouponCenter.vue no longer duplicates a basic Button with raw <button> elements (Constitution §2.3)', () => {
  const couponCenter = readSrc('src/views/CouponCenter.vue')
  assert.ok(!couponCenter.includes('<button type="button"'), 'no raw <button> should remain -- this file already uses van-button everywhere else, retry actions must match')
  assert.ok(couponCenter.includes('<van-button size="small" plain class="hero-retry-btn" @click="loadPreview">重试</van-button>'), 'the hero-card retry action must use van-button')
  assert.ok(couponCenter.includes('<van-button size="small" plain type="primary" @click="loadTemplates">重试</van-button>'), 'the manual-coupon-list retry action must use van-button')
})

test('CouponCenter.vue still has exactly one padded content wrapper distinct from the sticky PageHeader', () => {
  const couponCenter = readSrc('src/views/CouponCenter.vue')
  assert.ok(couponCenter.includes('<div class="page-content">'), 'page padding must live on an inner wrapper, not on the element PageHeader sits inside of')
  const style = couponCenter.split('<style scoped>', 2)[1] || ''
  assert.ok(!/\.coupon-page\s*\{[^}]*padding/.test(style), '.coupon-page itself must not carry padding now that PageHeader is a direct child of it')
  assert.ok(/\.page-content\s*\{[^}]*padding/.test(style), '.page-content must carry the padding that used to live on .coupon-page')
})

if (failures.length) {
  console.error(`Phase-04 governance failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-04 component adoption governance: passed')
