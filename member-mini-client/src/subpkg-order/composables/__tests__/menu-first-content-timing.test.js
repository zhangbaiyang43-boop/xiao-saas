import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const menuSource = readFileSync(
  fileURLToPath(new URL('../../pages/menu.vue', import.meta.url)),
  'utf8',
)

describe('P0-MENU-PERFORMANCE-IMPLEMENTATION-PHASE-02', () => {
  it('does not keep the skeleton over a cached or already-rendered menu while shop context loads', () => {
    expect(menuSource).not.toContain('loading || (!orderingContextReady && !orderingContextFailed)')
    expect(menuSource).toMatch(/<DishList[\s\S]*?:loading="loading"/)
    expect(menuSource).toMatch(/<LoadingStates[\s\S]*?:loading="loading"/)
  })

  it('records first_content from category and dish nodes without recording interactive in the same callback', () => {
    expect(menuSource).toContain('observeMenuFirstContent')
    expect(menuSource).toContain("definition: 'category_and_dish_nodes_observed'")
    expect(menuSource).not.toContain("definition: 'category_and_dish_actions_available'")
    const firstContentFn = menuSource.slice(
      menuSource.indexOf('const observeMenuFirstContent'),
      menuSource.indexOf('const recordMenuInteractive'),
    )
    expect(firstContentFn).toContain("markEventOnce('first_content'")
    expect(firstContentFn).not.toContain("markEventOnce('interactive'")
  })

  it('records interactive only after orderingContextReady is true', () => {
    expect(menuSource).toContain('recordMenuInteractive')
    expect(menuSource).toContain("definition: 'ordering_context_ready'")
    expect(menuSource).toMatch(/this\.orderingContextReady = true\s*\n\s*await observeMenuFirstContent\(this, pagePerfKey\)\s*\n\s*recordMenuInteractive\(this, pagePerfKey\)/)
    const interactiveFn = menuSource.slice(
      menuSource.indexOf('const recordMenuInteractive'),
      menuSource.indexOf('const wxLogin'),
    )
    expect(interactiveFn).toContain('if (!page?.orderingContextReady) return false')
    expect(interactiveFn).toContain("markEventOnce('interactive'")
    expect(interactiveFn).not.toContain("markEventOnce('first_content'")
  })

  it('observes first content from cached dishes without waiting for the menu network response', () => {
    const loadMenuFn = menuSource.slice(
      menuSource.indexOf('const loadMenu = async'),
      menuSource.indexOf('watch(cartItems'),
    )
    expect(loadMenuFn).toMatch(/if \(hadCacheHit\) \{[\s\S]*observeFirstContentNow\(\)/)
    expect(loadMenuFn.indexOf('observeFirstContentNow()')).toBeLessThan(loadMenuFn.indexOf('await getMenuItems'))
    expect(loadMenuFn).toContain('await getMenuItems(shopId.value)')
  })

  it('treats applied shop cache as valid context when the shop refresh fails', () => {
    const loadShopFn = menuSource.slice(
      menuSource.indexOf('const loadShopSettings = async'),
      menuSource.indexOf('const menuCacheKey'),
    )
    expect(loadShopFn).toContain('if (cachedData) applyShopInfoState(cachedData)')
    expect(loadShopFn).toContain('await getShopInfo(shopId.value)')
    expect(loadShopFn).toContain('return Boolean(cachedData)')
  })

  it('keeps add-to-cart and spec sheet gated on orderingContextReady', () => {
    expect(menuSource.match(/if \(!orderingContextReady\.value\)/g)).toHaveLength(2)
    expect(menuSource).toContain('orderingContextReady.value && totalCount.value > 0')
  })
})
