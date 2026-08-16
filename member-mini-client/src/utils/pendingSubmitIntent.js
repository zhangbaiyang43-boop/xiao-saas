// P0-15-01: durable create-order submit intent.
//
// Problem this closes: pendingSubmitRequestId (useCheckout.js) previously lived
// only in an in-memory Vue ref. If the create-order request reached and was
// committed by the server but the app process was killed before the response
// arrived -- or, more commonly, the user simply closed and reopened the cart
// sheet between a lost response and their retry tap -- the in-memory key was
// gone. A retry then minted a NEW request_id, and the server's
// (tenant_id, client_request_id) idempotency (P0-04) has no way to recognize
// it as the same business intent: it creates a genuine duplicate Order.
//
// This module persists the request_id AND the frozen, canonical create-order
// business payload (never a credential) to uni storage BEFORE the request is
// sent, keyed by tenant+table+dining_session_id -- the same scoping
// discipline already used by the pending-payment cache (see useCheckout.js's
// pendingPaymentStorageKey, P0-10).
//
// P0-15 FINAL CLOSURE, two properties this module exists to guarantee:
//
// 1. FAIL CLOSED ON UNRECORDABLE INTENT: savePendingSubmitIntent() returns
//    false on a storage write failure. Callers MUST check this and refuse to
//    send the create-order request at all when it fails -- sending a mutation
//    the client cannot durably identify is exactly the P0-15-01 failure mode,
//    just reached via a storage fault instead of a process kill. Likewise,
//    restorePendingSubmitIntent() distinguishes "no record" from "a record
//    exists for this scope but can't be read back reliably" (corrupt JSON,
//    missing requestId) -- corrupt must NOT be treated as "nothing pending":
//    that would let a caller assume a fresh identity and resend under it
//    while the real prior attempt's outcome is still genuinely unknown.
//
// 2. ONE request_id = ONE IMMUTABLE BUSINESS PAYLOAD: the frozen snapshot,
//    once saved, is what every retry under that request_id must resend --
//    never a payload rebuilt from a (possibly since-mutated) live cart. This
//    is deliberately NOT sufficient on its own for correctness: the server's
//    existing P0-04 fingerprint-conflict recovery remains the second line of
//    defense (see useCheckout.p0-04-idempotency.test.js) for any case this
//    client-side freeze doesn't cover.
//
// This is NOT a general offline-order queue: nothing here ever auto-fires a
// create-order request. Restoring only makes the NEXT explicit, user-triggered
// retry reuse the same identity + payload -- never on app launch.

const STORAGE_PREFIX = 'pending_order_submit_'

function storageKey(tenantId, tableNo, sessionId) {
  if (!tenantId || !sessionId) return null
  return STORAGE_PREFIX + tenantId + '_' + (tableNo || '') + '_' + sessionId
}

export function savePendingSubmitIntent({ tenantId, tableNo, sessionId, requestId, snapshot }) {
  const key = storageKey(tenantId, tableNo, sessionId)
  if (!key || !requestId) return false
  try {
    uni.setStorageSync(key, JSON.stringify({
      version: 1,
      requestId,
      snapshot: snapshot || null,
      createdAt: Date.now(),
    }))
    return true
  } catch (e) {
    return false
  }
}

// Returns one of:
//   { status: 'missing' }                    -- no record for this scope
//   { status: 'found', record: {...} }        -- a valid, readable record
//   { status: 'corrupt' }                     -- a record exists but cannot
//                                                 be relied on (bad JSON, or
//                                                 missing its requestId)
export function restorePendingSubmitIntent({ tenantId, tableNo, sessionId }) {
  const key = storageKey(tenantId, tableNo, sessionId)
  if (!key) return { status: 'missing' }
  let raw
  try {
    raw = uni.getStorageSync(key)
  } catch (e) {
    return { status: 'corrupt' }
  }
  if (!raw) return { status: 'missing' }
  let record
  try {
    record = JSON.parse(raw)
  } catch (e) {
    return { status: 'corrupt' }
  }
  if (!record?.requestId) return { status: 'corrupt' }
  return { status: 'found', record }
}

export function clearPendingSubmitIntent({ tenantId, tableNo, sessionId }) {
  const key = storageKey(tenantId, tableNo, sessionId)
  if (!key) return
  // eslint-disable-next-line no-empty
  try { uni.removeStorageSync(key) } catch (e) {}
}
