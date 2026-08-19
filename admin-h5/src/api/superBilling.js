import superRequest from './superRequest'

const BASE = '/super/billing'

function superHeaders(superToken) {
  return { 'X-Super-Token': superToken }
}

export async function listManualPayments(superToken, reviewStatus = 'WAITING_CONFIRMATION') {
  return superRequest.get(`${BASE}/manual-payments`, {
    params: { review_status: reviewStatus },
    headers: superHeaders(superToken),
  })
}

export async function confirmManualPayment(superToken, paymentId, note) {
  return superRequest.post(
    `${BASE}/manual-payments/${paymentId}/confirm`,
    { note: note || undefined },
    { headers: superHeaders(superToken) },
  )
}

export async function rejectManualPayment(superToken, paymentId, note) {
  return superRequest.post(
    `${BASE}/manual-payments/${paymentId}/reject`,
    { note: note || undefined },
    { headers: superHeaders(superToken) },
  )
}
