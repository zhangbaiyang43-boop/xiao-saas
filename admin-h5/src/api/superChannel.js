import axios from 'axios'

const BASE = '/api/super/channel'

function superHeaders(superToken) {
  return { 'X-Super-Token': superToken }
}

export async function listChannelPartners(superToken) {
  return axios.get(`${BASE}/partners`, { headers: superHeaders(superToken) })
}

export async function createChannelPartner(superToken, payload) {
  return axios.post(`${BASE}/partners`, payload, { headers: superHeaders(superToken) })
}
