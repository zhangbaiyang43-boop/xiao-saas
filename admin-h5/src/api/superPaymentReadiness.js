import superRequest from './superRequest'

export function getSuperPaymentReadiness(superToken, tenantId) {
  return superRequest.get(
    `/super/merchants/${encodeURIComponent(tenantId)}/payment-readiness`,
    { headers: { 'X-Super-Token': superToken } },
  )
}
