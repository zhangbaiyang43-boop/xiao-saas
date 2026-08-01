import request from './request'

export const getCustomerCoupons = (status = '', options = {}) => {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return request({
    url: `/v1/member/coupons${query}`,
    method: 'GET',
    authRedirect: options.authRedirect
  })
}

export const getCouponDetail = (id) => {
  return request({
    url: `/v1/member/coupons/${id}`,
    method: 'GET'
  })
}

export const remindMeForCoupon = (id) => {
  return request({
    url: `/v1/member/coupons/${id}/remind-me`,
    method: 'POST',
    authRedirect: false
  })
}
