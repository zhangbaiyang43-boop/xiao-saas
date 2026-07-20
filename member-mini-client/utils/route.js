export const requireCustomerLogin = () => {
  if (!uni.getStorageSync('customer_token')) {
    uni.reLaunch({ url: '/pages/index/index' })
    return false
  }
  return true
}
