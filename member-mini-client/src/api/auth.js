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

// clientId/participantToken 是可选的——带上之后，后端会顺手把这一桌的会话一起建好、
// 跟入口码解析结果一起返回，省掉扫码进店时"先解析入口码、再单独建会话"这两次串行网络
// 往返。不带这两个参数（或者后端识别不到 entry_type=='table'）时行为不变，返回结果里
// 就不会有 dining_session_id 这些字段，调用方要退回去单独调 resolveDiningSession。
export const resolveEntranceCode = (scene, { clientId, participantToken } = {}) => {
  const params = [`scene=${encodeURIComponent(scene)}`]
  if (clientId) params.push(`client_id=${encodeURIComponent(clientId)}`)
  if (participantToken) params.push(`participant_token=${encodeURIComponent(participantToken)}`)
  return request({
    url: `/v1/entrance-codes/resolve?${params.join('&')}`,
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
