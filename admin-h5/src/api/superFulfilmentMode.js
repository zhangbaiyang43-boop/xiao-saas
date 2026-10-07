import superRequest from './superRequest'

export function updateSuperFulfilmentMode(superToken, tenantId, mode, reason) {
  return superRequest.patch(
    `/super/merchants/${encodeURIComponent(tenantId)}/fulfilment-mode`,
    { mode, reason: String(reason || '').trim() },
    { headers: { 'X-Super-Token': superToken } },
  )
}
