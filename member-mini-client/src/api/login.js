export { loginOrCreateMember as login, loginOrCreateMember as register } from './auth'

export const logout = () => {
  uni.removeStorageSync('customer_token')
  uni.removeStorageSync('tenant_id')
  uni.removeStorageSync('customer_id')
  return Promise.resolve({ code: 200, msg: '退出成功', data: null })
}
