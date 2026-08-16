import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

// menu.vue is an SFC and can't be imported/executed by vitest here (no Vue-SFC
// compiler plugin wired into vitest.config.js) -- same pattern as
// menu-cart-context-wiring.test.js / menu-order-lock-wiring.test.js: pin the
// exact source text instead of executing it. The actual request_id
// persist/restore *logic* is covered by
// useCheckout.p0-15-durable-intent.test.js, which imports and executes the
// real useCheckout.js module directly -- this file only proves menu.vue
// doesn't undermine that mechanism by resetting the in-memory ref on ordinary
// cart-panel open/close.
const menuSource = readFileSync(
  fileURLToPath(new URL('../menu.vue', import.meta.url)),
  'utf8',
)

describe('menu.vue submit-intent wiring (P0-15-01)', () => {
  // ---- T02: cart close/reopen must not mint a new request_id for an
  // unresolved (ambiguous) pending create-order intent ----
  it('openCart() no longer resets pendingSubmitRequestId -- closing and reopening the cart must not change an in-flight submit identity', () => {
    const openCartStart = menuSource.indexOf('const openCart = () => {')
    expect(openCartStart).toBeGreaterThan(-1)
    const openCartEnd = menuSource.indexOf('\n    }', openCartStart)
    const openCartBody = menuSource.slice(openCartStart, openCartEnd)
    expect(openCartBody).not.toMatch(/pendingSubmitRequestId\.value\s*=\s*''/)
  })
})
