import request from './request'

export const getCouponVerifyCode = (couponId) => {
  return request({
    url: `/v1/miniapp/member/coupons/${couponId}/verify-code`,
    method: 'GET'
  })
}

export const createVerification = (data) => {
  return request({
    url: '/v1/verify',
    method: 'POST',
    data
  })
}
