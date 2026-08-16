// P0-03-03: process-lifetime cart snapshot cache, module-scoped and in-memory
// only (same pattern as request.js's `isRedirectingLogin` -- a plain
// module-level singleton, which this app's runtime keeps alive across page
// navigations within one running process; it does not survive an app
// relaunch/kill, which is intentional -- see the P0-03 audit's explicit
// MVP scope: same-process route re-entry only, never a permanent cart).
//
// Deliberately NOT uni storage: a plain in-memory object can't be corrupted
// by an external process and naturally evaporates on relaunch, so none of
// the "corrupted persisted data" handling a storage-backed cache would need
// applies here.
//
// Restore requires an EXACT match on tenant_id + table_no + dining_session_id.
// Any mismatch (including either side simply missing a field) discards
// silently rather than ever handing back a cart for a different context --
// this is the mechanism that keeps tenant/table/session isolation true after
// introducing persistence (Phase A's PASS verdicts assumed no persistence at
// all and cannot be reused without this guarantee).

let cachedContext = null
let cachedCart = null
let cachedSpecCartItems = null

const isCompleteContext = (context) => Boolean(
  context && context.tenant_id && context.table_no && context.dining_session_id
)

const sameContext = (a, b) => (
  a.tenant_id === b.tenant_id && a.table_no === b.table_no && a.dining_session_id === b.dining_session_id
)

export function saveCartSnapshot(context, cart, specCartItems) {
  if (!isCompleteContext(context)) return
  cachedContext = { tenant_id: context.tenant_id, table_no: context.table_no, dining_session_id: context.dining_session_id }
  cachedCart = { ...(cart || {}) }
  cachedSpecCartItems = (specCartItems || []).map((item) => ({ ...item }))
}

export function restoreCartSnapshot(context) {
  if (!isCompleteContext(context)) return null
  if (!cachedContext || !sameContext(cachedContext, context)) return null
  return {
    cart: { ...cachedCart },
    specCartItems: cachedSpecCartItems.map((item) => ({ ...item })),
  }
}

export function clearCartSnapshot() {
  cachedContext = null
  cachedCart = null
  cachedSpecCartItems = null
}
