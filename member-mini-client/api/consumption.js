import request from './request'

export const getMemberConsumptions = () => {
  return request({
    url: '/v1/member/consumptions',
    method: 'GET'
  })
}
