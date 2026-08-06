import { config } from '../config'
import { recordSample } from '../utils/perf'
import { reportError } from '../utils/monitor'

// 第0批性能埋点：只认这两个 URL，命中就顺手记一笔耗时，不用改任何调用方。
// 后端已经在响应头里带了 X-Process-Time-Ms（服务端处理耗时），一并存进 meta 里，
// 跟客户端整体耗时（含网络往返）对比，能看出慢是慢在网络还是慢在后端处理。
const METRIC_URL_MATCHERS = [
  { metric: 'menu_api', test: (url, method) => url === '/v1/menu/items' && method === 'GET' },
  { metric: 'submit_order', test: (url, method) => url === '/v1/orders' && method === 'POST' },
]

function matchMetric(url, method) {
  const hit = METRIC_URL_MATCHERS.find((m) => m.test(url, method))
  return hit ? hit.metric : null
}

function readProcessTimeMs(header) {
  if (!header) return undefined
  const raw = header['X-Process-Time-Ms'] ?? header['x-process-time-ms']
  const n = Number(raw)
  return Number.isFinite(n) ? n : undefined
}

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

  const metric = matchMetric(options.url, (options.method || 'GET').toUpperCase())
  const startedAt = Date.now()

  return new Promise((resolve, reject) => {
    uni.request({
      ...options,
      url: config.apiBaseUrl + options.url,
      header,
      success: (res) => {
        const body = res.data || {}
        const statusCode = res.statusCode || 0

        if (statusCode >= 200 && statusCode < 300 && body.code === 200) {
          if (metric) {
            recordSample(metric, Date.now() - startedAt, {
              url: options.url,
              serverMs: readProcessTimeMs(res.header),
            })
          }
          resolve(body)
          return
        }

        if (body.code === 401 || statusCode === 401 || body.code === 403 || statusCode === 403) {
          const error = new Error(toFriendlyMessage('', statusCode))
          error.statusCode = statusCode || body.code
          error.code = body.code || statusCode
          // 401/403 大多是"登录态过期"这种预期内的正常事件，不是代码 bug，
          // 单独用 auth_error 这个 scene 报，方便以后在后台把它跟真正的接口
          // 故障分开看，不要混在一起互相掩盖。
          reportError('api.auth_error', error, { url: options.url })
          if (authRedirect) redirectToGuest()
          reject(error)
          return
        }

        const error = new Error(toFriendlyMessage(body.msg || body.message || body.detail, statusCode))
        error.statusCode = statusCode
        error.code = body.code
        reportError('api.error', error, { url: options.url, statusCode, code: body.code })
        reject(error)
      },
      fail: (err) => {
        const error = new Error(toFriendlyMessage(err.errMsg))
        reportError('api.network_fail', error, { url: options.url, errMsg: err.errMsg })
        reject(error)
      }
    })
  })
}

export default request