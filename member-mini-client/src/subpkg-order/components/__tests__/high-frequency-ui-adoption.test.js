import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../../../')
const read = (rel) => readFileSync(path.join(srcRoot, rel), 'utf8')

describe('P1-HIGH-FREQUENCY-UI-ADOPTION-PHASE-02', () => {
  const dishList = read('subpkg-order/components/DishList.vue')
  const loadingStates = read('subpkg-order/components/LoadingStates.vue')
  const bottomNav = read('subpkg-order/components/BottomNav.vue')
  const bubble = read('components/order-bubble/order-bubble.vue')
  const cartBar = read('subpkg-order/components/CartBar.vue')
  const checkout = read('subpkg-order/components/CheckoutSheet.vue')
  const homeTab = read('subpkg-order/components/HomeTab.vue')

  it('migrates menu empty state onto StateEmpty', () => {
    expect(dishList).toMatch(/import\s+StateEmpty\s+from\s+['"]@\/components\/state-empty\/state-empty\.vue['"]/)
    expect(dishList).toMatch(/components\s*:\s*\{[^}]*StateEmpty/)
    expect(dishList).toContain('<state-empty')
    expect(dishList).toContain('title="暂无菜品"')
    expect(dishList).toContain("@action=\"$emit('retry-load')\"")
    expect(dishList).toContain('/static/order/empty-menu.png')
    expect(dishList).not.toContain('class="empty-retry"')
    expect(dishList).not.toContain('empty-title')
  })

  it('migrates dish-card price onto PriceText md', () => {
    expect(dishList).toMatch(/import\s+PriceText\s+from\s+['"]\.\/PriceText\.vue['"]/)
    expect(dishList).toMatch(/components\s*:\s*\{[^}]*PriceText/)
    expect(dishList).toMatch(/<price-text[\s\S]*size="md"/)
    expect(dishList).not.toContain('class="dish-price-currency"')
    expect(dishList).not.toContain('class="dish-price-amount"')
    expect(dishList).not.toContain('class="dish-price-suffix"')
  })

  it('migrates menu error onto StateError and drops the loading copy', () => {
    expect(loadingStates).toMatch(/import\s+StateError\s+from\s+['"]@\/components\/state-error\/state-error\.vue['"]/)
    expect(loadingStates).toMatch(/components\s*:\s*\{[^}]*StateError/)
    expect(loadingStates).toContain('<state-error')
    expect(loadingStates).toContain('title="菜单加载失败"')
    expect(loadingStates).toContain("@retry=\"$emit('retry-load')\"")
    expect(loadingStates).not.toContain('菜单加载中...')
    expect(loadingStates).not.toContain('class="retry-btn"')
    expect(loadingStates).toContain('skeleton-mask')
    expect(loadingStates).toMatch(/z-index:\s*2000/)
  })

  it('replaces chrome and floating z-index literals with existing layer tokens', () => {
    expect(bottomNav).toMatch(/z-index:\s*var\(--z-chrome\)/)
    expect(bottomNav).not.toMatch(/z-index:\s*300/)
    expect(bubble).toMatch(/\.ob-area[\s\S]*z-index:\s*var\(--z-floating\)/)
    expect(bubble).not.toMatch(/z-index:\s*850\b/)
  })

  it('does not change CartBar chrome, checkout CTA height, or HomeTab featured price', () => {
    expect(cartBar).toMatch(/z-index:\s*320/)
    expect(cartBar).toContain('background: #1f2937')
    expect(cartBar).toMatch(/\.checkout-btn\s*\{[\s\S]*height:\s*92rpx/)
    expect(checkout).toMatch(/\.checkout-btn-full\s*\{[\s\S]*height:\s*104rpx/)
    expect(homeTab).toContain('class="ht-feature-amount"')
    expect(homeTab).not.toMatch(/import\s+PriceText/)
    expect(homeTab).not.toContain('<price-text')
  })
})
