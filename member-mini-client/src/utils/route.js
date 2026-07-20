export const requireCustomerLogin = () => {
  if (!uni.getStorageSync('customer_token')) {
    uni.reLaunch({ url: '/pages/mine/mine' })
    return false
  }
  return true
}

