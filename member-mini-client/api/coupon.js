import request from './request'

export const getCustomerCoupons = (status = '') => {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return request({
    url: `/v1/member/coupons${query}`,
    method: 'GET'
  })
}

export const getCouponDetail = (id) => {
  return request({
    url: `/v1/member/coupons/${id}`,
    method: 'GET'
  })
}
