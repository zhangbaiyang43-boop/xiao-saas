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

const normalizeErrorMessage = (payload) => {
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  if (typeof payload === 'object') {
    return payload.message || payload.msg || payload.detail || payload.code || JSON.stringify(payload)
  }
  return String(payload)
}

const toFriendlyMessage = (message, statusCode = 0) => {
  const raw = normalizeErrorMessage(message)
  if (statusCode === 401) return '\u767b\u5f55\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165'
  if (statusCode === 403) return '\u767b\u5f55\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165'
  if (statusCode === 404) return '\u8bf7\u6c42\u7684\u5185\u5bb9\u4e0d\u5b58\u5728\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5'
  if (statusCode >= 500) return '\u95e8\u5e97\u7cfb\u7edf\u6b63\u5728\u5fd9\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5'
  if (!raw) return '\u7f51\u7edc\u4e0d\u7a33\u5b9a\uff0c\u8bf7\u518d\u8bd5\u4e00\u6b21'
  if (technicalPatterns.some((item) => raw.includes(item))) return '\u95e8\u5e97\u7cfb\u7edf\u6b63\u5728\u5fd9\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5'
  if (raw.includes('request:fail') || raw.includes('ERR_FAILED')) return '\u7f51\u7edc\u4e0d\u7a33\u5b9a\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u518d\u8bd5'
  return raw
}

let _redirectingToGuest = false

const redirectToGuest = () => {
  if (_redirectingToGuest) return
  _redirectingToGuest = true
  uni.removeStorageSync('customer_token')
  uni.removeStorageSync('customer_id')
  uni.removeStorageSync('is_new_customer')
  uni.removeStorageSync('customer_profile')
  uni.showToast({ title: '\u767b\u5f55\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u626b\u7801\u8fdb\u5165', icon: 'none' })
  setTimeout(() => {
    uni.reLaunch({
      url: '/pages/mine/mine',
      complete: () => { _redirectingToGuest = false }
    })
  }, 1200)
}

const request = (options) => {
  const token = uni.getStorageSync('customer_token')
  const authRedirect = options.authRedirect !== false
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

        if (statusCode >= 200 && statusCode < 300 && body.code === 200) {
          resolve(body)
          return
        }

        if (body.code === 401 || statusCode === 401 || body.code === 403 || statusCode === 403) {
          const error = new Error(toFriendlyMessage('', statusCode))
          error.statusCode = statusCode || body.code
          error.code = body.code || statusCode
          if (authRedirect) redirectToGuest()
          reject(error)
          return
        }

        const error = new Error(toFriendlyMessage(body.msg || body.message || body.detail, statusCode))
        error.statusCode = statusCode
        error.code = body.code
        reject(error)
      },
      fail: (err) => {
        reject(new Error(toFriendlyMessage(err.errMsg)))
      }
    })
  })
}

export default request