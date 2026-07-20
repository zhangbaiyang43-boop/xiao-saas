import { getMemberProfile } from './auth'
import request from './request'

export const getCustomerInfo = getMemberProfile
export const getCustomerById = getMemberProfile

export const getCustomerTimeline = () => {
  return request({
    url: '/v1/member/consumptions',
    method: 'GET'
  })
}
