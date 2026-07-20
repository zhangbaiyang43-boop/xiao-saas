﻿﻿﻿﻿﻿import axios from 'axios'

const getBaseURL = () => {
  const envBaseURL = import.meta.env.VITE_API_BASE_URL
  const hostname = window.location.hostname

  if (hostname === 'saas.zhangbaiyang.com') {
    return '/api'
  }

  return envBaseURL || '/api'
}

const baseURL = getBaseURL()
const pendingRequests = new Map()

const stableStringify = (value) => {
  if (!value) return ''
  try {
    return JSON.stringify(value, Object.keys(value).sort())
  } catch {
    return String(value)
  }
}

const requestKey = (config) => {
  const method = String(config.method || 'get').toUpperCase()
  return [
    method,
    config.baseURL || '',
    config.url || '',
    stableStringify(config.params),
    stableStringify(config.data),
  ].join('|')
}

const devLog = (message, data) => {
  if (import.meta.env.DEV) console.info(message, data)
}

const convertIdsToString = (data) => {
  if (!data) return data

  if (Array.isArray(data)) {
    return data.map(item => convertIdsToString(item))
  }

  if (typeof data === 'object') {
    const result = {}
    for (const key in data) {
      const value = data[key]
      if (key === 'id' ||
          key === 'template_id' ||
          key === 'customer_id' ||
          key === 'consumption_id' ||
          key === 'coupon_template_id' ||
          key === 'tenant_id' ||
          key.endsWith('_id')) {
        result[key] = String(value ?? '')
      } else {
        result[key] = convertIdsToString(value)
      }
    }
    return result
  }

  return data
}

const instance = axios.create({
  baseURL: baseURL,
  timeout: 10000,
  transformResponse: [(data) => {
    try {
      const parsed = JSON.parse(data)
      return convertIdsToString(parsed)
    } catch {
      return data
    }
  }]
})

instance.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    const meta = config.meta || {}
    const shouldDedupe = Boolean(meta.fromPolling || meta.dedupe)
    const key = meta.dedupeKey || requestKey(config)
    config.meta = {
      ...meta,
      requestKey: key,
      startedAt: performance.now(),
      page: window.location.pathname,
    }
    if (shouldDedupe && pendingRequests.has(key)) {
      const error = new Error('duplicate request skipped')
      error.__duplicateSkipped = true
      error.config = config
      devLog('[request] skipped duplicate', {
        url: config.url,
        page: config.meta.page,
        fromPolling: Boolean(meta.fromPolling),
      })
      return Promise.reject(error)
    }
    if (shouldDedupe) pendingRequests.set(key, true)
    return config
  },
  error => Promise.reject(error)
)

instance.interceptors.response.use(
  response => {
    const meta = response.config?.meta || {}
    if (meta.requestKey) pendingRequests.delete(meta.requestKey)
    const duration = Math.round(performance.now() - (meta.startedAt || performance.now()))
    devLog('[request] completed', {
      url: response.config?.url,
      duration,
      fromPolling: Boolean(meta.fromPolling),
      page: meta.page,
    })
    return response.data
  },
  error => {
    const meta = error.config?.meta || {}
    if (meta.requestKey) pendingRequests.delete(meta.requestKey)
    if (error.__duplicateSkipped) {
      return Promise.reject(error)
    }
    if (import.meta.env.DEV || !error.response) {
      console.error('API Error:', error)
    }
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('tenant_id')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default instance
