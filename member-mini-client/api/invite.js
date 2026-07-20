import request from './request'

export const getInviteSummary = () => {
  return request({
    url: '/v1/miniapp/member/invite',
    method: 'GET'
  })
}

export const getCommissionRecords = () => {
  return request({
    url: '/v1/miniapp/member/commission-records',
    method: 'GET'
  })
}
