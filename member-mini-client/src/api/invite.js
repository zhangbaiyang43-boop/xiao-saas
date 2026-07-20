import request from './request'

export const getInviteSummary = () =>
  request({ url: '/v1/miniapp/invite/summary', method: 'GET' })

export const getInviteRecords = (params) =>
  request({ url: '/v1/miniapp/invite/records', method: 'GET', data: params })

export const bindInviter = (data) =>
  request({ url: '/v1/miniapp/invite/bind', method: 'POST', data })

// Legacy — kept for any existing callers
export const getCommissionRecords = () =>
  request({ url: '/v1/miniapp/member/commission-records', method: 'GET' })
