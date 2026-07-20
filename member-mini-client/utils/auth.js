export const hasCustomerToken = () => Boolean(uni.getStorageSync('customer_token'))

export const saveCustomerSession = (data) => {
  uni.setStorageSync('customer_token', data.token)
  uni.setStorageSync('tenant_id', data.tenant_id)
  uni.setStorageSync('customer_id', data.customer_id)
  const welcomeCoupon = data.new_customer_coupon || data.coupon
  if (welcomeCoupon) {
    uni.setStorageSync('welcome_coupon', JSON.stringify(welcomeCoupon))
    uni.setStorageSync('is_new_customer', 'true')
    uni.setStorageSync('coupon_modal_shown', 'false')
  } else if (data.is_new_customer) {
    uni.setStorageSync('is_new_customer', 'true')
    uni.setStorageSync('coupon_modal_shown', 'false')
  }
}

export const clearCustomerSession = () => {
  uni.removeStorageSync('customer_token')
  uni.removeStorageSync('tenant_id')
  uni.removeStorageSync('customer_id')
  uni.removeStorageSync('is_new_customer')
  uni.removeStorageSync('coupon_modal_shown')
  uni.removeStorageSync('welcome_coupon')
}
