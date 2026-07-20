export const hasCustomerToken = () => Boolean(uni.getStorageSync('customer_token'))

export const saveCustomerSession = (data) => {
  uni.setStorageSync('customer_token', data.token)
  uni.setStorageSync('tenant_id', data.tenant_id)
  uni.setStorageSync('customer_id', data.customer_id)
  const phone = data.phone || data.customer?.phone || data.profile?.phone || ''
  if (phone) uni.setStorageSync('customer_phone', phone)
  const profile = data.profile || data.customer || null
  if (profile) {
    uni.setStorageSync('customer_profile', JSON.stringify({
      ...profile,
      id: String(profile.id || data.customer_id || ''),
      tenant_id: data.tenant_id,
      phone
    }))
  }
  const isNewCustomer = data.is_new_customer === true || data.is_new_customer === 'true'
  const welcomeCoupon = data.new_customer_coupon || (isNewCustomer ? data.coupon : null)
  if (isNewCustomer) {
    uni.setStorageSync('is_new_customer', 'true')
    uni.setStorageSync('coupon_modal_shown', 'false')
    if (welcomeCoupon) {
      uni.setStorageSync('welcome_coupon', JSON.stringify(welcomeCoupon))
    }
  }
}

export const clearCustomerSession = () => {
  uni.removeStorageSync('customer_token')
  uni.removeStorageSync('tenant_id')
  uni.removeStorageSync('customer_id')
  uni.removeStorageSync('customer_phone')
  uni.removeStorageSync('customer_profile')
  uni.removeStorageSync('is_new_customer')
  uni.removeStorageSync('coupon_modal_shown')
  uni.removeStorageSync('welcome_coupon')
}
