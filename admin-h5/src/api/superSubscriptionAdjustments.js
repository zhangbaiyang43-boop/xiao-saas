import superRequest from './superRequest'

function headers(superToken) {
  return { 'X-Super-Token': superToken }
}

function basePath(tenantId) {
  return `/super/merchants/${encodeURIComponent(tenantId)}/subscription-adjustments`
}

export function previewSubscriptionAdjustment(superToken, tenantId, payload) {
  return superRequest.post(`${basePath(tenantId)}/preview`, payload, { headers: headers(superToken) })
}

export function commitSubscriptionAdjustment(superToken, tenantId, payload) {
  return superRequest.post(basePath(tenantId), payload, { headers: headers(superToken) })
}

export function listSubscriptionAdjustments(superToken, tenantId) {
  return superRequest.get(basePath(tenantId), {
    params: { limit: 20 },
    headers: headers(superToken),
  })
}
