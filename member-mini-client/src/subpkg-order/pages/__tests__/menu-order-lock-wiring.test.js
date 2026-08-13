import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

// P0-04-02: menu.vue is an SFC and can't be imported/executed by vitest here
// (no Vue-SFC compiler plugin wired into vitest.config.js). Same pattern as
// menu-table-context.test.js / menu-cart-context-wiring.test.js: pin the exact
// source text instead of executing it. confirmSpec's ordering guard (the same
// underlying mechanism, just reached through useSpecSheet.js) IS directly
// executed in useSpecSheet.test.js's "P0-04 C02/C03" cases -- this file only
// covers the guards that live inline in menu.vue itself.
const menuSource = readFileSync(
  fileURLToPath(new URL('../menu.vue', import.meta.url)),
  'utf8',
)

describe('menu.vue submit-in-flight cart lock (P0-04-02)', () => {
  it('addToCart is a no-op while a submit is in flight', () => {
    const idx = menuSource.indexOf('const addToCart = (dish) => {')
    expect(idx).toBeGreaterThan(-1)
    const body = menuSource.slice(idx, idx + 600)
    expect(body).toMatch(/if \(ordering\.value\) return/)
  })

  it('removeFromCart is a no-op while a submit is in flight', () => {
    const idx = menuSource.indexOf('const removeFromCart = (dish) => {')
    expect(idx).toBeGreaterThan(-1)
    const body = menuSource.slice(idx, idx + 400)
    expect(body).toMatch(/if \(ordering\.value\) return/)
  })

  it('increaseCartItem is a no-op while a submit is in flight', () => {
    const idx = menuSource.indexOf('const increaseCartItem = (item) => {')
    expect(idx).toBeGreaterThan(-1)
    const body = menuSource.slice(idx, idx + 400)
    expect(body).toMatch(/if \(ordering\.value\) return/)
  })

  it('clearCart is a no-op while a submit is in flight', () => {
    const idx = menuSource.indexOf('const clearCart = () => {')
    expect(idx).toBeGreaterThan(-1)
    const body = menuSource.slice(idx, idx + 400)
    expect(body).toMatch(/if \(ordering\.value\) return/)
  })

  it('openSpecSheet is a no-op while a submit is in flight', () => {
    const idx = menuSource.indexOf('const openSpecSheet = (dish) => {')
    expect(idx).toBeGreaterThan(-1)
    const body = menuSource.slice(idx, idx + 400)
    expect(body).toMatch(/if \(ordering\.value\) return/)
  })

  it('useSpecSheet is wired with the same ordering ref menu.vue uses for its own guards', () => {
    expect(menuSource).toMatch(/formatPrice, ordering,/)
  })
})
