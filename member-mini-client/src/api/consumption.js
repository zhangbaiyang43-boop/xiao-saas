import request from './request'

export const getMemberConsumptions = () => {
  return request({
    url: '/v1/member/consumptions',
    method: 'GET'
  })
}

export const getConsumptionDetail = (id) => {
  return request({
    url: `/v1/member/consumptions/${id}`,
    method: 'GET'
  })
}
