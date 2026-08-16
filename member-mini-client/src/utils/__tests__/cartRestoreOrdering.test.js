import { describe, it, expect, beforeEach } from 'vitest'
import { ref, watch, nextTick } from 'vue'
import { saveCartSnapshot, restoreCartSnapshot, clearCartSnapshot } from '../cartContextCache.js'

// P0-03 T11-T14, under REAL active-watcher timing -- not just testing
// cartContextCache.js's save/restore in isolation (that's cartContextCache.
// test.js), but the actual reactive sequence menu.vue drives: a `watch` over
// [cart, specCartItems, diningSessionId] that saves on change, racing against
// an async ensureDiningSession() that sets diningSessionId mid-flight, then a
// restoreCartIfSameContext() call once it resolves.
//
// This exposed a real bug during reconciliation: diningSessionId is one of
// the watch's own sources, so ensureDiningSession() setting it fires the
// watcher (with cart.value still {}) *before* restore gets a chance to run,
// saving an empty snapshot over whatever a previous instance had left behind.
// The fix (mirrored here, and in the real menu.vue) is a `cartHydrated` guard:
// the watcher's save is suppressed until restoreCartIfSameContext has run
// once, regardless of how many times cart/specCartItems/diningSessionId
// change before that.
function buildPageInstance({ shopId, tableNo, initialSessionId = '' }) {
  const cart = ref({})
  const specCartItems = ref([])
  const diningSessionId = ref(initialSessionId)
  const cartHydrated = ref(false)

  watch([cart, specCartItems, diningSessionId], () => {
    if (!cartHydrated.value) return
    saveCartSnapshot(
      { tenant_id: shopId, table_no: tableNo, dining_session_id: diningSessionId.value },
      cart.value, specCartItems.value,
    )
  }, { deep: true })

  const restoreCartIfSameContext = () => {
    if (Object.keys(cart.value).length || specCartItems.value.length) {
      cartHydrated.value = true
      return
    }
    const restored = restoreCartSnapshot({ tenant_id: shopId, table_no: tableNo, dining_session_id: diningSessionId.value })
    if (restored) {
      cart.value = restored.cart
      specCartItems.value = restored.specCartItems
    }
    cartHydrated.value = true
  }

  // Mirrors ensureDiningSession(): resolves a session id asynchronously,
  // setting the ref mid-function (before its own promise settles) -- the
  // exact shape that produced the race.
  const resolveSession = async (sessionId) => {
    await Promise.resolve()
    diningSessionId.value = sessionId
    await Promise.resolve()
    return true
  }

  const onLoad = async (sessionId) => {
    await resolveSession(sessionId)
    restoreCartIfSameContext()
    await nextTick()
  }

  return { cart, specCartItems, diningSessionId, onLoad }
}

describe('cart restore ordering under active watcher (P0-03 T11-T14)', () => {
  beforeEach(() => {
    clearCartSnapshot()
  })

  it('T11: same tenant+table+session -- restore succeeds despite the watcher firing mid-init (SAVE_BEFORE_RESTORE_RACE regression guard)', async () => {
    saveCartSnapshot({ tenant_id: 'A', table_no: 'A12', dining_session_id: 'S1' }, { dishA: 2 }, [
      { specKey: 'dishB-k1', id: 'dishB', qty: 1 },
    ])

    const page2 = buildPageInstance({ shopId: 'A', tableNo: 'A12' })
    await page2.onLoad('S1')

    expect(page2.cart.value).toEqual({ dishA: 2 })
    expect(page2.specCartItems.value).toEqual([{ specKey: 'dishB-k1', id: 'dishB', qty: 1 }])
  })

  it('T12: table switch -- no restore, and subsequent mutation only ever saves under the NEW context', async () => {
    saveCartSnapshot({ tenant_id: 'A', table_no: 'A01', dining_session_id: 'S1' }, { dishA: 2 }, [])

    const page2 = buildPageInstance({ shopId: 'A', tableNo: 'A08' })
    await page2.onLoad('S2')

    expect(page2.cart.value).toEqual({})

    // A real mutation after hydration must save under A08/S2 only, never
    // resurrecting or blending with A01/S1's content.
    page2.cart.value = { dishC: 1 }
    await nextTick()

    const a01Restore = restoreCartSnapshot({ tenant_id: 'A', table_no: 'A01', dining_session_id: 'S1' })
    const a08Restore = restoreCartSnapshot({ tenant_id: 'A', table_no: 'A08', dining_session_id: 'S2' })
    expect(a01Restore).toBeNull() // A01/S1's old snapshot got overwritten by the shared singleton, not leaked forward
    expect(a08Restore).toEqual({ cart: { dishC: 1 }, specCartItems: [] })
  })

  it('T13: tenant switch -- no restore', async () => {
    saveCartSnapshot({ tenant_id: 'A', table_no: 'A01', dining_session_id: 'S1' }, { dishA: 2 }, [])

    const page2 = buildPageInstance({ shopId: 'B', tableNo: 'B01' })
    await page2.onLoad('Sx')

    expect(page2.cart.value).toEqual({})
  })

  it('T14: same tenant/table, session changes (next diner) -- no restore', async () => {
    saveCartSnapshot({ tenant_id: 'A', table_no: 'A03', dining_session_id: 'S1' }, { dishA: 1 }, [])

    const page2 = buildPageInstance({ shopId: 'A', tableNo: 'A03' })
    await page2.onLoad('S2')

    expect(page2.cart.value).toEqual({})
  })
})
