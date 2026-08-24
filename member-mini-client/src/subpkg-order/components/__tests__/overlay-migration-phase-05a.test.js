import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../../../')
const read = (rel) => readFileSync(path.join(srcRoot, rel), 'utf8')

describe('P1-OVERLAY-MIGRATION-PHASE-05A', () => {
  const coupon = read('subpkg-order/components/CouponPicker.vue')
  const checkout = read('subpkg-order/components/CheckoutSheet.vue')
  const spec = read('subpkg-order/components/SpecSheet.vue')
  const success = read('subpkg-order/components/PaymentSuccessSheet.vue')
  const welcome = read('subpkg-order/components/WelcomeCouponSheet.vue')
  const contracts = readFileSync(
    path.resolve(here, '../../../../scripts/check-ui-contracts.mjs'),
    'utf8',
  )

  it('migrates CouponPicker shell onto BaseSheet blocking-top', () => {
    expect(coupon).toMatch(/import\s+BaseSheet\s+from\s+['"]@\/components\/base-sheet\/base-sheet\.vue['"]/)
    expect(coupon).toMatch(/<base-sheet\b/)
    expect(coupon).toMatch(/layer=["']blocking-top["']/)
    expect(coupon).toContain("@close=\"$emit('cancel')\"")
    expect(coupon).not.toMatch(/class=["']mask["']/)
    expect(coupon).not.toMatch(/class=["']mask\s/)
    expect(coupon).not.toMatch(/@click\.stop/)
    expect(coupon).toContain("$emit('select-coupon'")
  })

  it('migrates CheckoutSheet shell onto BaseSheet blocking with footer', () => {
    expect(checkout).toMatch(/import\s+BaseSheet\s+from\s+['"]@\/components\/base-sheet\/base-sheet\.vue['"]/)
    expect(checkout).toMatch(/<base-sheet\b/)
    expect(checkout).toMatch(/layer=["']blocking["']/)
    expect(checkout).not.toMatch(/layer=["']blocking-top["']/)
    expect(checkout).toContain('<template #footer>')
    expect(checkout).toContain("@close=\"$emit('close')\"")
    expect(checkout).toContain("@click=\"$emit('checkout')\"")
    expect(checkout).toMatch(/\.checkout-btn-full\s*\{[\s\S]*height:\s*104rpx/)
    expect(checkout).not.toMatch(/class=["']mask["']/)
    expect(checkout).not.toMatch(/class=["']mask\s/)
    expect(checkout).not.toMatch(/@click\.stop/)
  })

  it('leaves Spec / Success / Welcome on legacy mask', () => {
    expect(spec).toMatch(/class=["']mask["']/)
    expect(success).toMatch(/class=["']mask\s/)
    expect(welcome).toMatch(/class=["']mask\s/)
    expect(spec).not.toMatch(/<base-sheet\b/)
    expect(success).not.toMatch(/<base-sheet\b/)
    expect(welcome).not.toMatch(/<base-sheet\b/)
  })

  it('drops CheckoutSheet and CouponPicker from LEGACY_MASK_ALLOWLIST', () => {
    const block = contracts.match(/export const LEGACY_MASK_ALLOWLIST = \[([\s\S]*?)\]/)
    expect(block, 'LEGACY_MASK_ALLOWLIST missing').toBeTruthy()
    const listed = block[1]
    expect(listed).not.toContain('CheckoutSheet.vue')
    expect(listed).not.toContain('CouponPicker.vue')
    expect(listed).toContain('PaymentSuccessSheet.vue')
    expect(listed).toContain('SpecSheet.vue')
    expect(listed).toContain('WelcomeCouponSheet.vue')
  })
})
