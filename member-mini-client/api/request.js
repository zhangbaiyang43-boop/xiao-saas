import { config } from '../config'

const technicalPatterns = [
  'Traceback',
  'CustomerService',
  'CustomerIdentity',
  'IntegrityError',
  'AttributeError',
  'Internal Server Error',
  'Network Error',
  'timeout'
]

const toFriendlyMessage = (message, statusCode = 0) => {
  const raw = String(message || '')
  if (statusCode === 401) return '登录已过期，请重新扫码进入'
  if (statusCode === 404) return '没有找到入口码，请重新扫码'
  if (statusCode >= 500) return '门店系统正在忙，请稍后再试'
  if (!raw) return '网络不稳定，请再试一次'
  if (technicalPatterns.some((item) => raw.includes(item))) return '门店系统正在忙，请稍后再试'
  if (raw.includes('request:fail') || raw.includes('ERR_FAILED')) return '网络不稳定，请检查网络后再试'
  return raw
}

const request = (options) => {
  const token = uni.getStorageSync('customer_token')
  const header = {
    'content-type': 'application/json',
    ...(options.header || {})
  }

  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  return new Promise((resolve, reject) => {
    uni.request({
      ...options,
      url: config.apiBaseUrl + options.url,
      header,
      success: (res) => {
        const body = res.data || {}
        const statusCode = res.statusCode || 0

        if (statusCode >= 200 && statusCode < 300 && body.code !== 401) {
          resolve(body)
          return
        }

        if (body.code === 401 || statusCode === 401 || body.code === 403 || statusCode === 403) {
          uni.removeStorageSync('customer_token')
          uni.removeStorageSync('customer_id')
          uni.removeStorageSync('is_new_customer')
        }

        reject(new Error(toFriendlyMessage(body.msg || body.detail, statusCode)))
      },
      fail: (err) => {
        reject(new Error(toFriendlyMessage(err.errMsg)))
      }
    })
  })
}

export default request
