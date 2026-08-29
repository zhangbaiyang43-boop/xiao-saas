import { config } from '../config'
import {
  capturePerformanceContext,
  markEvent,
  recordInvalidMeasurement,
  recordSample,
  validatePerformanceContext,
} from '../utils/perf'
import { reportError } from '../utils/monitor'

// Only fixed, low-cardinality ordering endpoints are measured. Dynamic IDs and the performance
// upload endpoint are deliberately excluded. X-Process-Time-Ms is server processing time;
// client minus server is only a NETWORK_APPROX diagnostic, never true network-layer timing.
const METRIC_URL_MATCHERS = [
  { metric: 'menu_api', apiName: 'menu_items', eventBase: 'menu_api', test: (url, method) => url === '/v1/menu/items' && method === 'GET' },
  { metric: 'shop_info_api', apiName: 'shop_info', eventBase: 'shop_info', test: (url, method) => url === '/v1/shop/info' && method === 'GET' },
  { metric: 'submit_order', apiName: 'submit_order', eventBase: 'submit_order', test: (url, method) => url === '/v1/orders' && method === 'POST' },
]

export function matchApiMetric(url, method) {
  const normalizedUrl = String(url || '').split('?')[0]
  if (normalizedUrl === '/api/v1/perf/report' || normalizedUrl === '/v1/perf/report') return null
  return METRIC_URL_MATCHERS.find((matcher) => matcher.test(normalizedUrl, String(method || 'GET').toUpperCase())) || null
}

export function readProcessTimeMs(header) {
  if (!header) return null
  const raw = header['X-Process-Time-Ms'] ?? header['x-process-time-ms']
  if (typeof raw !== 'string' && typeof raw !== 'number') return null
  const normalized = typeof raw === 'string' ? raw.trim() : raw
  if (normalized === '' || (typeof normalized === 'string' && !/^\d+(\.\d+)?$/.test(normalized))) return null
  const n = Number(normalized)
  return Number.isFinite(n) && n >= 0 ? n : null
}

// P0-16 Phase B1: pairs a customer-reported error with the backend's own
// correlation identifiers -- requestId (server-minted, from the X-Request-ID
// response header) and clientRequestId (the P0-04 idempotency key this
// request itself carried) -- so a support screenshot can be matched against
// backend logs. requestId is null (not an error) when there was no response
// at all, e.g. a genuine network failure.
export function extractCorrelationIds(options, header) {
  const clientRequestId = (options && options.data && options.data.request_id) || null
  const requestId = header ? (header['X-Request-ID'] ?? header['x-request-id'] ?? null) : null
  return { requestId, clientRequestId }
}

export function classifyRequestFailure(errMsg) {
  const message = String(errMsg || '').toLowerCase()
  if (message.includes('timeout')) return { status: 'timeout', errorType: 'timeout' }
  if (message.includes('abort')) return { status: 'abort', errorType: 'abort' }
  return { status: 'failure', errorType: message ? 'network' : 'unknown' }
}

function recordApiTelemetry(matcher, method, startedAt, perfContext, { status, httpStatus = null, errorType = null, header } = {}) {
  if (!matcher) return
  try {
    const endedAt = Date.now()
    const validity = validatePerformanceContext(perfContext, endedAt)
    if (validity !== 'valid') {
      recordInvalidMeasurement(matcher.metric, validity, {
        api_name: matcher.apiName,
        status,
      }, endedAt)
      return
    }
    const clientMs = Math.max(endedAt - startedAt, 0)
    const serverMs = readProcessTimeMs(header)
    const networkApproxMs = serverMs === null ? null : Math.max(clientMs - serverMs, 0)
    const meta = {
      api_name: matcher.apiName,
      method,
      client_ms: clientMs,
      server_ms: serverMs,
      network_approx_ms: networkApproxMs,
      status,
      http_status: httpStatus,
      error_type: errorType,
    }
    recordSample(matcher.metric, clientMs, meta)
    markEvent(`${matcher.eventBase}_${status === 'success' ? 'success' : 'failure'}`, meta)
  } catch {
    // Performance telemetry is a sidecar and must never change request resolution/rejection.
  }
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
  // \u515c\u5e95\uff1a\u9762\u5411\u987e\u5ba2\u7684\u9519\u8bef\u6587\u6848\u4e00\u5b9a\u662f\u4e2d\u6587\u3002\u4e00\u4e2a\u6c49\u5b57\u90fd\u6ca1\u6709 = \u5185\u90e8/\u6280\u672f\u4e32
  // \uff08"dining session not found"\u3001"forbidden" \u4e4b\u7c7b\uff09\uff0c\u522b\u539f\u6837\u5f39\u7ed9\u987e\u5ba2\u770b\u3002
  if (!/[\u4e00-\u9fff]/.test(raw)) return '\u64cd\u4f5c\u6ca1\u6210\u529f\uff0c\u8bf7\u91cd\u8bd5\u6216\u544a\u77e5\u670d\u52a1\u5458'
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

  const method = (options.method || 'GET').toUpperCase()
  const metric = matchApiMetric(options.url, method)
  const startedAt = Date.now()
  let perfContext = metric ? capturePerformanceContext(startedAt) : null
  if (metric) {
    try {
      const startValidity = perfContext ? validatePerformanceContext(perfContext, startedAt) : 'missing_session'
      // A request that starts after foreground idle expiry begins a fresh diagnostic session.
      // A request started while suspended must stay invalid and must not reactivate telemetry.
      if (startValidity !== 'background_interrupted') {
        markEvent(`${metric.eventBase}_start`, { api_name: metric.apiName, method }, startedAt)
        perfContext = capturePerformanceContext(startedAt)
      }
    } catch { /* sidecar only */ }
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
          recordApiTelemetry(metric, method, startedAt, perfContext, {
            status: 'success',
            httpStatus: statusCode,
            errorType: null,
            header: res.header,
          })
          resolve(body)
          return
        }

        recordApiTelemetry(metric, method, startedAt, perfContext, {
          status: 'failure',
          httpStatus: statusCode || null,
          errorType: statusCode >= 200 && statusCode < 300 ? 'unknown' : 'http',
          header: res.header,
        })

        if (body.code === 401 || statusCode === 401 || body.code === 403 || statusCode === 403) {
          // authRedirect:false（如员工 bind preview）用服务端业务文案，避免误显示「登录已过期」。
          const message = authRedirect
            ? toFriendlyMessage('', statusCode)
            : (body.msg || body.message || body.detail || toFriendlyMessage('', statusCode))
          const error = new Error(message)
          error.statusCode = statusCode || body.code
          error.code = body.code || statusCode
          error.bizCode = body?.data?.code
          error.data = body?.data
          // 401/403 大多是"登录态过期"这种预期内的正常事件，不是代码 bug，
          // 单独用 auth_error 这个 scene 报，方便以后在后台把它跟真正的接口
          // 故障分开看，不要混在一起互相掩盖。
          reportError('api.auth_error', error, { url: options.url, ...extractCorrelationIds(options, res.header) })
          if (authRedirect) redirectToGuest()
          reject(error)
          return
        }

        const error = new Error(toFriendlyMessage(body.msg || body.message || body.detail, statusCode))
        error.statusCode = statusCode
        error.code = body.code
        error.bizCode = body?.data?.code
        reportError('api.error', error, { url: options.url, statusCode, code: body.code, ...extractCorrelationIds(options, res.header) })
        reject(error)
      },
      fail: (err) => {
        const classification = classifyRequestFailure(err?.errMsg)
        recordApiTelemetry(metric, method, startedAt, perfContext, {
          status: classification.status,
          httpStatus: null,
          errorType: classification.errorType,
        })
        const error = new Error(toFriendlyMessage(err.errMsg))
        reportError('api.network_fail', error, { url: options.url, errMsg: err.errMsg, ...extractCorrelationIds(options, undefined) })
        reject(error)
      }
    })
  })
}

export default request
