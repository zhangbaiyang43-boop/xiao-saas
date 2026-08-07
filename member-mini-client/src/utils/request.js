// src/utils/request.js

// 开发环境：本地 H5 可用 localhost
// 真机/微信开发者工具建议改成你的电脑局域网 IP，例如：http://192.168.1.10:9898
const BASE_URL = 'https://api.zhangbaiyang.com'

let isRedirectingLogin = false

const getToken = () => {
  return uni.getStorageSync('customer_token') || ''
}

const goLogin = () => {
  if (isRedirectingLogin) return

  isRedirectingLogin = true
  uni.removeStorageSync('customer_token')
  uni.removeStorageSync('customer_id')

  uni.showToast({
    title: '登录已过期，请重新扫码进入',
    icon: 'none'
  })

  setTimeout(() => {
    uni.reLaunch({
      url: '/pages/mine/mine',
      complete: () => {
        isRedirectingLogin = false
      }
    })
  }, 500)
}

const isSuccessResponse = (data) => {
  return data && (
    data.code === 200 ||
    data.code === 0 ||
    data.success === true
  )
}

const getErrorMessage = (data, fallback = '请求失败') => {
  if (!data) return fallback
  return data.msg || data.message || data.error || fallback
}

const request = (options = {}) => {
  const token = getToken()

  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${options.url}`,
      method: options.method || 'GET',
      data: options.data || {},
      timeout: options.timeout || 15000,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.header || {})
      },
      success: (res) => {
        const data = res.data || {}

        if (res.statusCode === 401 || data.code === 401) {
          goLogin()
          reject(new Error('登录已失效'))
          return
        }

        if (res.statusCode < 200 || res.statusCode >= 300) {
          const message = getErrorMessage(data, `请求失败：${res.statusCode}`)
          uni.showToast({ title: message, icon: 'none' })
          reject(new Error(message))
          return
        }

        if (isSuccessResponse(data)) {
          resolve(data.data !== undefined ? data.data : data)
          return
        }

        const message = getErrorMessage(data)
        uni.showToast({ title: message, icon: 'none' })
        reject(new Error(message))
      },
      fail: (err) => {
        const message = err.errMsg || '网络异常，请检查后端服务是否启动'
        uni.showToast({ title: message, icon: 'none' })
        reject(err)
      }
    })
  })
}

export const miniappApi = {
  getProfile: () => request({
    url: '/api/miniapp/member/profile'
  }),

  getCoupons: () => request({
    url: '/api/miniapp/member/coupons'
  }),

  getPointsLogs: () => request({
    url: '/api/miniapp/member/points/logs'
  }),

  getCouponVerifyCode: (couponId) => request({
    url: `/api/miniapp/member/coupons/${couponId}/verify-code`
  })
}

export default request
