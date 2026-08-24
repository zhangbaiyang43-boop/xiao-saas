import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(fileURLToPath(new URL('../../..', import.meta.url)))
const src = path.join(root, 'src')
const read = (rel) => readFileSync(path.join(src, rel), 'utf8')

describe('P1 design token consolidation', () => {
  it('removes the third brand green from live CTA styles', () => {
    const files = [
      'pages/entry/index.vue',
      'subpkg-order/components/MemberCheckoutChoice.vue',
      'subpkg-order/components/CheckoutAuthSheet.vue',
    ]
    files.forEach((rel) => {
      const source = read(rel)
      expect(source, rel).not.toContain('#16c76f')
      expect(source, rel).toContain('var(--brand)')
    })
  })

  it('moves member and coupon page brand greens onto --brand', () => {
    const files = [
      'subpkg-member/pages/card.vue',
      'subpkg-member/pages/orders.vue',
      'subpkg-member/pages/consumptions.vue',
      'subpkg-member/pages/consumption-detail.vue',
      'subpkg-member/pages/profile-edit.vue',
      'subpkg-member/pages/invite.vue',
      'subpkg-member/pages/points.vue',
      'subpkg-member/pages/growth.vue',
      'subpkg-member/pages/staff-share.vue',
      'subpkg-coupon/pages/list.vue',
      'subpkg-coupon/pages/detail.vue',
    ]
    files.forEach((rel) => {
      const source = read(rel)
      expect(source, rel).not.toMatch(/#07C160|#07c160|#059f4f/)
      expect(source, rel).toContain('var(--brand)')
    })
  })

  it('moves State* colors onto existing tokens', () => {
    const empty = read('components/state-empty/state-empty.vue')
    const error = read('components/state-error/state-error.vue')
    const loading = read('components/state-loading/state-loading.vue')

    expect(empty).toContain('color: var(--text-1)')
    expect(empty).toContain('color: var(--text-3)')
    expect(empty).toContain('background: var(--brand)')
    expect(empty).not.toMatch(/#07C160|#333|#9ca3af/)

    expect(error).toContain('color: var(--text-1)')
    expect(error).toContain('color: var(--text-3)')
    expect(error).toContain('background: var(--brand)')
    expect(error).not.toMatch(/#07C160|#111827/)

    expect(loading).toContain('border-top-color: var(--brand)')
    expect(loading).toContain('border: 6rpx solid var(--brand-light)')
    expect(loading).toContain('color: var(--text-1)')
    expect(loading).toContain('color: var(--text-3)')
    expect(loading).not.toMatch(/#07C160|#111827|#d1fae5/)
  })
})
