import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

// menu.vue is an SFC and can't be imported/executed by vitest here (no Vue-SFC
// compiler plugin wired into vitest.config.js). Same pattern as
// menu-table-context.test.js: pin the exact source text instead of executing
// it. The actual save/restore *logic* (context-matching, discard-on-mismatch)
// is covered by cartContextCache.test.js, which imports and executes the real
// module directly -- this file only proves menu.vue wires that module in at
// the right points.
const menuSource = readFileSync(
  fileURLToPath(new URL('../menu.vue', import.meta.url)),
  'utf8',
)

describe('menu.vue cart-context wiring (P0-03-03)', () => {
  it('imports the process-lifetime cart snapshot cache', () => {
    expect(menuSource).toMatch(/import\s*\{\s*saveCartSnapshot,\s*restoreCartSnapshot\s*\}\s*from\s*['"]@\/utils\/cartContextCache\.js['"]/)
  })

  it('saves a snapshot whenever cart or specCartItems change, keyed by tenant+table+session', () => {
    expect(menuSource).toMatch(/watch\(\[cart, specCartItems, diningSessionId\]/)
    expect(menuSource).toMatch(/tenant_id:\s*shopId\.value,\s*table_no:\s*tableNo\.value,\s*dining_session_id:\s*diningSessionId\.value/)
  })

  it('only restores when the current instance cart is still empty (never clobbers in-flight edits)', () => {
    expect(menuSource).toMatch(/if\s*\(Object\.keys\(cart\.value\)\.length\s*\|\|\s*specCartItems\.value\.length\)\s*\{/)
  })

  it('restore is invoked from onLoad only after ensureDiningSession has resolved', () => {
    const idx = menuSource.indexOf('await this.ensureDiningSession(false)')
    const restoreIdx = menuSource.indexOf('this.restoreCartIfSameContext()')
    expect(idx).toBeGreaterThan(-1)
    expect(restoreIdx).toBeGreaterThan(idx)
  })

  it('P0-03 reconciliation: cartHydrated guard suppresses saves until restore has had its turn (SAVE_BEFORE_RESTORE_RACE fix)', () => {
    // diningSessionId is itself a watch source, so ensureDiningSession()
    // setting it fires the watcher (cart.value still {}) before restore
    // runs -- without this guard, that fires an empty save that clobbers
    // whatever a previous instance had left in the cache. See
    // cartRestoreOrdering.test.js for the executed proof.
    expect(menuSource).toMatch(/const cartHydrated = ref\(false\)/)
    expect(menuSource).toMatch(/if \(!cartHydrated\.value\) return/)
    expect(menuSource).toMatch(/cartHydrated\.value = true/)
  })
})
