import request from './request'

export const loginOrCreateMember = (data) => {
  return request({
    url: '/v1/member/login-or-create',
    method: 'POST',
    data
  })
}

export const joinByEntranceCode = (data) => {
  return request({
    url: '/v1/miniapp/entry/join',
    method: 'POST',
    data
  })
}

export const getMemberProfile = () => {
  return request({
    url: '/v1/member/profile',
    method: 'GET'
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
