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
// This module persists the request_id (plus scope and a non-sensitive payload
// snapshot) to uni storage BEFORE the create-order request is sent, keyed by
// tenant+table+dining_session_id -- the same scoping discipline already used
// by the pending-payment cache (see useCheckout.js's pendingPaymentStorageKey,
// P0-10). It deliberately does NOT persist participant_token or any other
// credential: those must always be re-read fresh from the current session
// context at retry time, never replayed from a stale local copy.
//
// This is NOT a general offline-order queue: nothing here ever auto-fires a
// create-order request. Restoring only makes the NEXT explicit, user-triggered
// retry reuse the same identity. If the rebuilt payload doesn't exactly match
// what the server actually received under that id, the server's existing
// P0-04 fingerprint-conflict recovery (already proven safe, see
// useCheckout.p0-04-idempotency.test.js) takes over and binds to the real
// existing order instead -- so this module's snapshot only needs to be good
// enough for traceability, not perfect reconstruction, for safety to hold.

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

export function restorePendingSubmitIntent({ tenantId, tableNo, sessionId }) {
  const key = storageKey(tenantId, tableNo, sessionId)
  if (!key) return null
  try {
    const raw = uni.getStorageSync(key)
    if (!raw) return null
    const record = JSON.parse(raw)
    if (!record?.requestId) return null
    return record
  } catch (e) {
    return null
  }
}

export function clearPendingSubmitIntent({ tenantId, tableNo, sessionId }) {
  const key = storageKey(tenantId, tableNo, sessionId)
  if (!key) return
  // eslint-disable-next-line no-empty
  try { uni.removeStorageSync(key) } catch (e) {}
}
