import request from './request'

/** Staff mini-program auth — does not use customer JWT as staff permission. */
const opts = { authRedirect: false }

export const getStaffMiniprogramStatus = () =>
  request({
    url: '/v1/staff/miniprogram/status',
    method: 'GET',
    ...opts,
  })

export const previewStaffMpBind = (scene) =>
  request({
    url: '/v1/staff/miniprogram/bind/preview',
    method: 'POST',
    data: { scene },
    ...opts,
  })

export const confirmStaffMpBind = (data) =>
  request({
    url: '/v1/staff/miniprogram/bind/confirm',
    method: 'POST',
    data,
    ...opts,
  })

export const staffMpLogin = (code) =>
  request({
    url: '/v1/staff/miniprogram/login',
    method: 'POST',
    data: { code },
    ...opts,
  })

export const staffMpLoginSelect = (data) =>
  request({
    url: '/v1/staff/miniprogram/login/select',
    method: 'POST',
    data,
    ...opts,
  })
