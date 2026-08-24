const EVENT_NAMES = new Set([
  'admin_page_enter',
  'admin_first_content_visible',
  'admin_page_ready',
  'admin_api_request_start',
  'admin_api_request_end',
])

const TARGET_PAGES = Object.freeze({
  Dashboard: 'Dashboard',
  OrderManage: 'OrderManage',
  MenuManage: 'DishManage',
  CustomerList: 'MemberManage',
})

const ENVIRONMENTS = new Set(['local', 'staging', 'production', 'unknown'])
const DEFAULT_MAX_EVENTS = 200

let idSequence = 0

function nextId(prefix, now) {
  idSequence = (idSequence + 1) % Number.MAX_SAFE_INTEGER
  return `${prefix}_${Number(now).toString(36)}_${idSequence.toString(36)}`
}

function normalizeEnvironment(value) {
  const normalized = String(value || '').toLowerCase()
  if (normalized === 'development' || normalized === 'dev') return 'local'
  return ENVIRONMENTS.has(normalized) ? normalized : 'unknown'
}

function normalizeVersion(value) {
  const normalized = String(value || '').trim()
  return normalized || 'unknown'
}

function normalizeRoute(value) {
  const raw = String(value || '')
  if (!raw) return '/unknown'
  try {
    const parsed = new URL(raw, 'https://admin.local')
    return parsed.pathname || '/'
  } catch {
    return raw.split(/[?#]/, 1)[0] || '/unknown'
  }
}

function normalizeDuration(value) {
  if (value === null || value === undefined || value === '') return null
  const duration = Number(value)
  return Number.isFinite(duration) && duration >= 0 ? Math.round(duration * 100) / 100 : null
}

function normalizeCount(value) {
  if (value === null || value === undefined || value === '') return null
  const count = Number(value)
  return Number.isFinite(count) && count >= 0 ? Math.round(count) : null
}

function routePage(route) {
  return TARGET_PAGES[String(route?.name || '')] || null
}

function defaultScheduleAfterRender(callback) {
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(callback)
    return
  }
  callback()
}

function currentRoutePath() {
  try {
    return normalizeRoute(window.location.pathname)
  } catch {
    return '/unknown'
  }
}

function normalizedApiPath(url) {
  const path = normalizeRoute(url)
  return path
    .split('/')
    .map((segment) => {
      if (/^\d+$/.test(segment)) return ':id'
      if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(segment)) return ':id'
      if (/^[0-9a-f]{24,}$/i.test(segment)) return ':id'
      return segment
    })
    .join('/')
}

export function matchAdminApiRequest(config = {}) {
  let path
  try {
    path = normalizedApiPath(config.url)
  } catch {
    return null
  }
  let apiGroup = null

  if (/^\/v1\/orders(?:\/|$)/.test(path)) apiGroup = 'orders'
  else if (/^\/v1\/(?:menu|dish-library)(?:\/|$)/.test(path)) apiGroup = 'menu'
  else if (/^\/v1\/(?:customers|membership)(?:\/|$)/.test(path)) apiGroup = 'members'
  else if (
    /^\/v1\/(?:coupons?|coupon-templates|marketing)(?:\/|$)/.test(path)
    || path === '/v1/tenant/marketing-preview'
    || path === '/v1/stats/marketing-effectiveness'
  ) apiGroup = 'marketing'

  if (!apiGroup) return null
  const method = String(config.method || 'GET').toUpperCase()
  return {
    api_group: apiGroup,
    endpoint: path,
    request_name: `${method} ${path}`,
  }
}

export function classifyAdminApiResponse(data) {
  if (data?.success === false) return 'business_error'
  if (data && Object.prototype.hasOwnProperty.call(data, 'code')) {
    return String(data.code) === '200' ? 'success' : 'business_error'
  }
  return 'success'
}

export function classifyAdminApiFailure(error = {}) {
  if (error.__duplicateSkipped) return 'duplicate_skipped'
  if (error.code === 'ERR_CANCELED' || error.name === 'CanceledError') return 'cancelled'
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT' || /timeout/i.test(String(error.message || ''))) {
    return 'timeout'
  }
  if (error.response) return 'http_error'
  return 'network_error'
}

export function readResponsePayloadSize(headers) {
  let raw = null
  try {
    raw = typeof headers?.get === 'function' ? headers.get('content-length') : null
  } catch {
    raw = null
  }
  if (raw === null || raw === undefined || raw === '') {
    raw = headers?.['content-length'] ?? headers?.['Content-Length'] ?? null
  }
  const value = Number(raw)
  if (raw !== null && raw !== '' && Number.isFinite(value) && value >= 0) {
    return { payload_size: Math.round(value), size_source: 'content_length' }
  }
  return { payload_size: null, size_source: 'unavailable' }
}

export function createAdminPerformanceCollector(options = {}) {
  const maxEvents = Math.max(1, Number(options.maxEvents) || DEFAULT_MAX_EVENTS)
  const now = typeof options.now === 'function' ? options.now : Date.now
  const clock = typeof options.clock === 'function'
    ? options.clock
    : () => (typeof performance?.now === 'function' ? performance.now() : Date.now())
  const scheduleAfterRender = typeof options.scheduleAfterRender === 'function'
    ? options.scheduleAfterRender
    : defaultScheduleAfterRender
  const environment = normalizeEnvironment(options.environment)
  const version = normalizeVersion(options.version)
  const devLog = typeof options.devLog === 'function' ? options.devLog : () => {}
  const events = []
  const listeners = new Set()
  let pendingNavigation = null
  let activeVisit = null

  function recordEvent(input = {}) {
    if (!EVENT_NAMES.has(input.event_name)) return null
    const event = Object.freeze({
      event_name: input.event_name,
      timestamp: new Date(Number(input.timestamp ?? now())).toISOString(),
      route: normalizeRoute(input.route || activeVisit?.route || currentRoutePath()),
      page: String(input.page || activeVisit?.page || 'unknown'),
      request_name: input.request_name ? String(input.request_name) : null,
      request_id: input.request_id ? String(input.request_id) : null,
      duration: normalizeDuration(input.duration),
      status: String(input.status || 'unknown'),
      payload_size: normalizeCount(input.payload_size),
      environment,
      version,
      visit_id: input.visit_id ? String(input.visit_id) : (activeVisit?.visit_id || null),
      api_group: input.api_group ? String(input.api_group) : null,
      size_source: input.size_source ? String(input.size_source) : null,
      data_count: normalizeCount(input.data_count),
    })

    events.push(event)
    if (events.length > maxEvents) events.splice(0, events.length - maxEvents)
    try { devLog('[admin-performance]', event) } catch { /* telemetry stays isolated */ }
    for (const listener of listeners) {
      try { listener(event) } catch { /* one subscriber cannot break another */ }
    }
    return event
  }

  function beginPageNavigation(route) {
    const page = routePage(route)
    pendingNavigation = page ? {
      page,
      route: normalizeRoute(route?.path),
      started_at: clock(),
      visit_id: nextId('visit', now()),
    } : null
    return pendingNavigation?.visit_id || null
  }

  function completePageNavigation(route, failure) {
    if (failure) {
      pendingNavigation = null
      return null
    }
    const page = routePage(route)
    if (!page) {
      pendingNavigation = null
      activeVisit = null
      return null
    }
    const completedAt = clock()
    const pending = pendingNavigation?.page === page
      ? pendingNavigation
      : {
          page,
          route: normalizeRoute(route?.path),
          started_at: completedAt,
          visit_id: nextId('visit', now()),
        }
    activeVisit = {
      ...pending,
      milestones: new Set(),
    }
    pendingNavigation = null
    return recordEvent({
      event_name: 'admin_page_enter',
      route: activeVisit.route,
      page: activeVisit.page,
      visit_id: activeVisit.visit_id,
      duration: completedAt - activeVisit.started_at,
      status: 'success',
    })
  }

  function markPageContentReady(details = {}) {
    if (!activeVisit || details.page !== activeVisit.page) return false
    if (activeVisit.milestones.has('content_ready_scheduled')) return false
    activeVisit.milestones.add('content_ready_scheduled')
    const visitId = activeVisit.visit_id
    scheduleAfterRender(() => {
      if (!activeVisit || activeVisit.visit_id !== visitId) return
      const duration = clock() - activeVisit.started_at
      const common = {
        route: activeVisit.route,
        page: activeVisit.page,
        visit_id: visitId,
        duration,
        status: details.status || 'unknown',
        data_count: details.data_count,
      }
      recordEvent({ event_name: 'admin_first_content_visible', ...common })
      recordEvent({ event_name: 'admin_page_ready', ...common })
      activeVisit.milestones.add('first_content_visible')
      activeVisit.milestones.add('page_ready')
    })
    return true
  }

  function startApiRequest(config = {}) {
    const match = matchAdminApiRequest(config)
    if (!match) return null
    const requestStartedAt = clock()
    const trace = Object.freeze({
      ...match,
      request_id: nextId('request', now()),
      started_at: requestStartedAt,
      route: activeVisit?.route || currentRoutePath(),
      page: activeVisit?.page || 'unknown',
      visit_id: activeVisit?.visit_id || null,
    })
    recordEvent({
      event_name: 'admin_api_request_start',
      ...trace,
      duration: null,
      status: 'started',
    })
    return trace
  }

  function finishApiRequest(trace, result = {}) {
    if (!trace?.request_id) return null
    return recordEvent({
      event_name: 'admin_api_request_end',
      route: trace.route,
      page: trace.page,
      visit_id: trace.visit_id,
      request_name: trace.request_name,
      request_id: trace.request_id,
      api_group: trace.api_group,
      duration: clock() - trace.started_at,
      status: result.status || 'unknown',
      payload_size: result.payload_size,
      size_source: result.size_source || 'unavailable',
    })
  }

  function subscribe(listener) {
    if (typeof listener !== 'function') return () => {}
    listeners.add(listener)
    return () => listeners.delete(listener)
  }

  return Object.freeze({
    recordEvent,
    beginPageNavigation,
    completePageNavigation,
    markPageContentReady,
    startApiRequest,
    finishApiRequest,
    subscribe,
    getEvents: () => events.map(event => ({ ...event })),
    clearEvents: () => events.splice(0, events.length),
  })
}

export function installAdminPerformanceDebugOutlet(target, getSnapshot) {
  if (!target || typeof getSnapshot !== 'function') return false

  try {
    if (Object.getOwnPropertyDescriptor(target, '__ADMIN_PERF_EVENTS__')) return false
    Object.defineProperty(target, '__ADMIN_PERF_EVENTS__', {
      configurable: false,
      enumerable: false,
      get() {
        try {
          const snapshot = getSnapshot()
          return Array.isArray(snapshot) ? snapshot : []
        } catch {
          return []
        }
      },
    })
    return true
  } catch {
    return false
  }
}

const viteEnvironment = import.meta.env?.VITE_ADMIN_ENVIRONMENT || import.meta.env?.MODE
const defaultEnvironment = normalizeEnvironment(viteEnvironment)
const defaultVersion = typeof __ADMIN_BUILD_VERSION__ !== 'undefined'
  ? __ADMIN_BUILD_VERSION__
  : 'unknown'
const defaultCollector = createAdminPerformanceCollector({
  environment: defaultEnvironment,
  version: defaultVersion,
  devLog: import.meta.env?.DEV && typeof console?.info === 'function'
    ? (...args) => console.info(...args)
    : () => {},
})

if (typeof window !== 'undefined') {
  installAdminPerformanceDebugOutlet(window, () => defaultCollector.getEvents())
}

export const beginPageNavigation = route => defaultCollector.beginPageNavigation(route)
export const completePageNavigation = (route, failure) => defaultCollector.completePageNavigation(route, failure)
export const markPageContentReady = details => defaultCollector.markPageContentReady(details)
export const startAdminApiRequest = config => defaultCollector.startApiRequest(config)
export const finishAdminApiRequest = (trace, result) => defaultCollector.finishApiRequest(trace, result)
export const subscribePerformanceEvents = listener => defaultCollector.subscribe(listener)
export const getPerformanceEvents = () => defaultCollector.getEvents()
export const clearPerformanceEvents = () => defaultCollector.clearEvents()
