import request from './request'

export const entryJoin = (data, options = {}) => {
  return request({
    url: '/v1/miniapp/entry/join',
    method: 'POST',
    data,
    authRedirect: options.authRedirect
  })
}

export const joinByEntranceCode = entryJoin

export const loginOrCreateMember = (data) => {
  return request({
    url: '/v1/member/login-or-create',
    method: 'POST',
    data
  })
}

export const getMemberProfile = (options = {}) => {
  return request({
    url: '/v1/member/profile',
    method: 'GET',
    authRedirect: options.authRedirect
  })
}

export const updateMemberProfile = (data) => {
  return request({
    url: '/v1/member/profile',
    method: 'PUT',
    data
  })
}

export const sendVerifyCode = (phone) => {
  return request({
    url: '/v1/member/send-verify-code',
    method: 'POST',
    data: { phone }
  })
}

export const bindPhone = (phone, code) => {
  return request({
    url: '/v1/member/bind-phone',
    method: 'POST',
    data: { phone, code }
  })
}

export const resolveEntranceCode = (scene) => {
  return request({
    url: `/v1/entrance-codes/resolve?scene=${encodeURIComponent(scene)}`,
    method: 'GET'
  })
}

export const getPointsHistory = (skip = 0, limit = 30) =>
  request({ url: `/v1/member/points?skip=${skip}&limit=${limit}`, method: 'GET' })

export const getMembershipGrowth = () =>
  request({ url: '/v1/member/membership', method: 'GET' })

export const getMyCoupons = (status = 'UNUSED') =>
  request({ url: `/v1/member/coupons?status=${status}&limit=100`, method: 'GET' })

export const resolveDiningSession = (data) => {
  return request({
    url: '/v1/dining-sessions/resolve',
    method: 'POST',
    data
  })
}

export const bindDiningParticipant = (data, options = {}) => {
  return request({
    url: '/v1/dining-sessions/participants/bind',
    method: 'POST',
    data,
    authRedirect: options.authRedirect
  })
}
