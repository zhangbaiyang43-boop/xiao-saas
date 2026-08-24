import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import {
  LEGACY_MASK_ALLOWLIST,
  hasExactClassToken,
} from '../../../../scripts/check-ui-contracts.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../../../')
const clientRoot = path.resolve(srcRoot, '..')

const readSrc = (rel) => readFileSync(path.join(srcRoot, rel), 'utf8')
const readClient = (rel) => readFileSync(path.join(clientRoot, rel), 'utf8')

const FORBIDDEN_BASE_SHEET_IMPORTS = [
  /from\s+['"]@\/api\//,
  /from\s+['"]@\/store\//,
  /from\s+['"].*useCheckout/,
  /from\s+['"]@\/subpkg-order\/pages\//,
  /from\s+['"]@\/pages\//,
  /from\s+['"]@\/subpkg-order\/composables\//,
]

describe('F2 BaseSheet first-family contract (static)', () => {
  const sheet = readSrc('components/base-sheet/base-sheet.vue')
  const overlay = readSrc('components/base-overlay/base-overlay.vue')
  const orderHistory = readSrc('subpkg-order/components/OrderHistorySheet.vue')
  const tableBill = readSrc('subpkg-order/components/TableBillSheet.vue')
  const shared = readSrc('subpkg-order/styles/_shared.scss')
  const constitution = readClient('docs/frontend/FRONTEND_CONSTITUTION.md')
  const overlayContract = readSrc('subpkg-order/components/__tests__/overlay-authority.contract.test.js')
  const f1cContract = readClient('scripts/__tests__/frontend-contracts.f1c.test.js')

  it('TEST A: BaseSheet uses BaseOverlay', () => {
    expect(sheet).toMatch(/import\s+BaseOverlay\s+from\s+['"]@\/components\/base-overlay\/base-overlay\.vue['"]/)
    expect(sheet).toMatch(/components\s*:\s*\{[\s\S]*BaseOverlay/)
    expect(sheet).toMatch(/<base-overlay\b/)
    expect(sheet).not.toMatch(/position\s*:\s*fixed/)
    expect(sheet).not.toMatch(/z-index\s*:/)
    expect(overlay).toMatch(/class="base-overlay-backdrop"/)
  })

  it('TEST B: BaseSheet blocking layer is passed through', () => {
    expect(sheet).toMatch(/:layer="layer"/)
    expect(sheet).toMatch(/layer\s*:\s*\{[\s\S]*default:\s*['"]blocking['"]/)
    expect(orderHistory).toMatch(/layer=["']blocking["']/)
    expect(tableBill).toMatch(/layer=["']blocking["']/)
    expect(orderHistory).not.toMatch(/layer=["']blocking-top["']/)
    expect(tableBill).not.toMatch(/layer=["']blocking-top["']/)
  })

  it('TEST C: mask click emits close', () => {
    expect(sheet).toMatch(/@mask-click="\$emit\('close'\)"/)
    expect(sheet).toMatch(/emits:\s*\[['"]close['"]\]/)
    expect(orderHistory).toMatch(/@close="\$emit\('close'\)"/)
    expect(tableBill).toMatch(/@close="emitCloseOrFinish"/)
  })

  it('TEST D: slot content click does not emit close', () => {
    const surfaceOpen = sheet.match(/<view\b[^>]*class="base-sheet-surface"[^>]*>/)
    expect(surfaceOpen, 'BaseSheet surface opening tag missing').toBeTruthy()
    expect(surfaceOpen[0]).not.toContain('@click')
    expect(sheet).not.toMatch(/<base-overlay[^>]*@click/)
    expect(sheet).toMatch(/<slot\s*\/>/)
    expect(orderHistory).not.toMatch(/@click\.stop/)
    expect(tableBill).not.toMatch(/@click\.stop/)
  })

  it('TEST E: OrderHistorySheet no longer has exact mask', () => {
    expect(hasExactClassToken(orderHistory, 'mask')).toBe(false)
    expect(orderHistory).toMatch(/import\s+BaseSheet\s+from\s+['"]@\/components\/base-sheet\/base-sheet\.vue['"]/)
    expect(orderHistory).toMatch(/<base-sheet\b/)
  })

  it('TEST F: TableBillSheet no longer has exact mask', () => {
    expect(hasExactClassToken(tableBill, 'mask')).toBe(false)
    expect(tableBill).toMatch(/import\s+BaseSheet\s+from\s+['"]@\/components\/base-sheet\/base-sheet\.vue['"]/)
    expect(tableBill).toMatch(/<base-sheet\b/)
  })

  it('TEST G: both files removed from LEGACY_MASK_ALLOWLIST', () => {
    expect(LEGACY_MASK_ALLOWLIST).toHaveLength(3)
    expect(LEGACY_MASK_ALLOWLIST).not.toContain('subpkg-order/components/OrderHistorySheet.vue')
    expect(LEGACY_MASK_ALLOWLIST).not.toContain('subpkg-order/components/TableBillSheet.vue')
    expect(LEGACY_MASK_ALLOWLIST).not.toContain('subpkg-order/components/CheckoutSheet.vue')
    expect(LEGACY_MASK_ALLOWLIST).not.toContain('subpkg-order/components/CouponPicker.vue')
    expect(LEGACY_MASK_ALLOWLIST).toEqual([
      'subpkg-order/components/PaymentSuccessSheet.vue',
      'subpkg-order/components/SpecSheet.vue',
      'subpkg-order/components/WelcomeCouponSheet.vue',
    ])
  })

  it('TEST H: dead .orders-sheet rules are gone from _shared.scss', () => {
    expect(shared).not.toMatch(/\.orders-sheet\b/)
    expect(shared).not.toMatch(/\.orders-sheet-head\b/)
    expect(shared).not.toMatch(/\.orders-sheet-title\b/)
    expect(shared).not.toMatch(/\.orders-sheet-close\b/)
    expect(shared).toMatch(/\.table-status-empty\b/)
    expect(constitution).toMatch(/BaseSheet/)
    expect(constitution).toMatch(/MUST compose BaseOverlay/)
    expect(constitution).toMatch(/requiring every BaseOverlay consumer to use BaseSheet/)
  })

  it('TEST I: BaseSheet does not import API / store / checkout / page / business modules', () => {
    for (const pattern of FORBIDDEN_BASE_SHEET_IMPORTS) {
      expect(sheet).not.toMatch(pattern)
    }
    expect(sheet).not.toMatch(/from\s+['"]@\/subpkg-order\/components\//)
    expect(sheet).not.toContain('useCheckout')
    expect(sheet).not.toContain('menu.vue')
  })

  it('TEST J: F1B / F1C contract files remain in the tree', () => {
    expect(overlayContract).toContain('TEST J: BaseOverlay owns backdrop mask-click without slot @click.stop')
    expect(overlayContract).toContain('TEST L: raw overlay detector rejects numeric and token z-index alike')
    expect(f1cContract).toContain('TEST 01: new class="mask" + shared import not on allowlist fails')
    expect(f1cContract).toContain('TEST C: main-old is not the main branch token')
  })
})
