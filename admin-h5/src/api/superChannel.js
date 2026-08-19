import superRequest from './superRequest'

const BASE = '/super/channel'

function superHeaders(superToken) {
  return { 'X-Super-Token': superToken }
}

export async function listChannelPartners(superToken) {
  return superRequest.get(`${BASE}/partners`, { headers: superHeaders(superToken) })
}

export async function createChannelPartner(superToken, payload) {
  return superRequest.post(`${BASE}/partners`, payload, { headers: superHeaders(superToken) })
}
