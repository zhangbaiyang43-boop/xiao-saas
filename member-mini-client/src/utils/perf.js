// App-internal performance telemetry. External QR recognition/platform launch time is not
// observable here and must never be described as scan latency.

const REPORT_URL = 'https://api.zhangbaiyang.com/api/v1/perf/report'
const STORAGE_PREFIX = 'perf_samples_'
const SESSION_KEY = 'perf_session_v1'
const STARTS_KEY = 'perf_starts_v1'
const TIMELINE_PREFIX = 'perf_timeline_'
const TIMELINE_INDEX_KEY = 'perf_timeline_sessions_v1'
const MAX_SAMPLES = 60
const MAX_TIMELINE_EVENTS = 100
const MAX_TIMELINE_SESSIONS = 5

// The common project request timeout is 15s. One minute leaves four request windows for the
// launch -> entry -> menu path while expiring the historical 110s contamination decisively.
export const PERF_SESSION_MAX_IDLE_MS = 60_000

const MAX_REASONABLE_DURATION_MS = {
  launch_to_entry: 60_000,
  entry_resolve: 60_000,
  entry_to_menu: 30_000,
  menu_onload_to_first_content: 60_000,
  menu_onload_to_interactive: 60_000,
  menu_api: 60_000,
  shop_info_api: 60_000,
  menu_processing: 10_000,
  first_content_to_interactive: 30_000,
  first_cart_response: 5_000,
  submit_order: 60_000,
}

const LEGACY_METRICS = [
  'scan_to_interactive',
  'stage_cold_start_to_onload',
  'stage_onload_to_menu_ready',
  'stage_menu_ready_to_render',
  'cart_open',
]

const DURATION_METRICS = Object.keys(MAX_REASONABLE_DURATION_MS)
const TRACKED_METRICS = [...LEGACY_METRICS, ...DURATION_METRICS]

let pendingBatch = []
let flushTimer = null
const FLUSH_BATCH_SIZE = 10
const FLUSH_DELAY_MS = 5000

const safeGet = (key, fallback = '') => {
  try {
    const value = uni.getStorageSync(key)
    return value === undefined || value === null ? fallback : value
  } catch {
    return fallback
  }
}

const safeSet = (key, value) => {
  try {
    uni.setStorageSync(key, value)
    return true
  } catch {
    return false
  }
}

const safeRemove = (key) => {
  try { uni.removeStorageSync(key) } catch { /* telemetry must never affect business flow */ }
}

const createPerfSessionId = () => `ps_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`

const normalizeLaunchType = (launchType) => (
  launchType === 'cold' || launchType === 'warm' ? launchType : 'unknown'
)

const readSession = () => {
  const session = safeGet(SESSION_KEY, null)
  return session && typeof session === 'object' && session.id ? session : null
}

const writeSession = (session) => {
  safeSet(SESSION_KEY, session)
  return session
}

const readStarts = () => {
  const starts = safeGet(STARTS_KEY, null)
  return starts && typeof starts === 'object' ? starts : {}
}

const readTimelineFor = (sessionId) => {
  const timeline = safeGet(TIMELINE_PREFIX + sessionId, null)
  return Array.isArray(timeline) ? timeline : []
}

const writeTimelineFor = (sessionId, timeline) => {
  if (timeline.length > MAX_TIMELINE_EVENTS) {
    timeline.splice(0, timeline.length - MAX_TIMELINE_EVENTS)
  }
  safeSet(TIMELINE_PREFIX + sessionId, timeline)
}

const readRuntimeDimensions = () => {
  let appVersion = 'unknown'
  let platform = 'unknown'
  try {
    const miniProgram = uni.getAccountInfoSync?.()?.miniProgram || {}
    appVersion = miniProgram.version || miniProgram.envVersion || 'unknown'
  } catch { /* best effort */ }
  try {
    platform = uni.getSystemInfoSync?.()?.platform || 'unknown'
  } catch { /* best effort */ }
  return { app_version: appVersion, platform }
}

const primeNetworkType = (sessionId) => {
  try {
    if (typeof uni.getNetworkType !== 'function') return
    uni.getNetworkType({
      success: (res) => {
        const session = readSession()
        if (!session || session.id !== sessionId) return
        session.network_type = res?.networkType || 'unknown'
        writeSession(session)
      },
      fail: () => {},
    })
  } catch { /* network detection is non-blocking and optional */ }
}

export function startPerformanceSession(launchType = 'unknown', now = Date.now()) {
  const session = {
    id: createPerfSessionId(),
    started_at: now,
    last_active_at: now,
    state: 'ACTIVE',
    launch_type: normalizeLaunchType(launchType),
    network_type: 'unknown',
    lifecycle_generation: 0,
    once: {},
  }
  const previousIds = safeGet(TIMELINE_INDEX_KEY, [])
  const timelineIds = [...(Array.isArray(previousIds) ? previousIds : []), session.id]
  while (timelineIds.length > MAX_TIMELINE_SESSIONS) {
    safeRemove(TIMELINE_PREFIX + timelineIds.shift())
  }
  safeSet(TIMELINE_INDEX_KEY, timelineIds)
  safeSet(STARTS_KEY, {})
  writeSession(session)
  primeNetworkType(session.id)
  return session
}

export function getPerformanceSession(now = Date.now()) {
  const session = readSession()
  if (!session) return null
  if (session.state === 'ACTIVE' && now - session.last_active_at > PERF_SESSION_MAX_IDLE_MS) {
    session.state = 'EXPIRED'
    session.expired_at = now
    writeSession(session)
  }
  return session
}

const ensureActiveSession = (now = Date.now()) => {
  const session = getPerformanceSession(now)
  if (session?.state === 'ACTIVE') return session
  return startPerformanceSession('unknown', now)
}

const appendTimelineEvent = (session, event, meta, now) => {
  const timeline = readTimelineFor(session.id)
  timeline.push({
    event,
    at: now,
    offset_ms: Math.max(now - session.started_at, 0),
    perf_session_id: session.id,
    meta: meta || undefined,
  })
  writeTimelineFor(session.id, timeline)
}

export function markEvent(event, meta, now = Date.now()) {
  try {
    if (!event) return null
    const session = ensureActiveSession(now)
    appendTimelineEvent(session, event, meta, now)
    session.last_active_at = now
    writeSession(session)
    return session
  } catch {
    return null
  }
}

export function markEventOnce(event, guardKey = event, meta, now = Date.now()) {
  try {
    const session = ensureActiveSession(now)
    session.once = session.once || {}
    if (session.once[guardKey]) return false
    session.once[guardKey] = true
    writeSession(session)
    markEvent(event, meta, now)
    return true
  } catch {
    return false
  }
}

export function handleAppHide(now = Date.now()) {
  const session = ensureActiveSession(now)
  markEvent('app_hide', undefined, now)
  const starts = readStarts()
  Object.keys(starts).forEach((name) => {
    appendTimelineEvent(session, 'duration_invalid', {
      metric: name,
      validity: 'background_interrupted',
    }, now)
  })
  safeSet(STARTS_KEY, {})
  session.lifecycle_generation = Number(session.lifecycle_generation || 0) + 1
  session.state = 'SUSPENDED'
  session.suspended_at = now
  session.last_active_at = now
  return writeSession(session)
}

export function handleAppShow(now = Date.now()) {
  let session = readSession()
  const resumeAt = Number(session?.suspended_at || session?.last_active_at || 0)
  const longResume = !session || now - resumeAt > PERF_SESSION_MAX_IDLE_MS

  if (longResume || session?.state === 'EXPIRED') {
    session = startPerformanceSession(session ? 'warm' : 'unknown', now)
  } else if (session.state === 'SUSPENDED') {
    session.state = 'ACTIVE'
    session.last_active_at = now
    delete session.suspended_at
    writeSession(session)
  }

  markEvent('app_show', { resume: Boolean(resumeAt) }, now)
  return readSession()
}

export function markStart(name, now = Date.now()) {
  try {
    if (!name) return null
    const session = ensureActiveSession(now)
    const starts = readStarts()
    starts[name] = { started_at: now, perf_session_id: session.id }
    safeSet(STARTS_KEY, starts)
    session.last_active_at = now
    writeSession(session)
    return starts[name]
  } catch {
    return null
  }
}

export function discardStart(name) {
  const starts = readStarts()
  if (!Object.prototype.hasOwnProperty.call(starts, name)) return false
  delete starts[name]
  safeSet(STARTS_KEY, starts)
  return true
}

export function capturePerformanceContext(now = Date.now()) {
  const session = readSession()
  if (!session) return null
  return {
    perfSessionId: session.id,
    lifecycleGeneration: Number(session.lifecycle_generation || 0),
    capturedAt: now,
  }
}

export function validatePerformanceContext(context, now = Date.now()) {
  if (!context) return 'missing_session'
  const session = readSession()
  if (!session || session.id !== context.perfSessionId) return 'invalid_session'
  if (session.state !== 'ACTIVE') return session.state === 'SUSPENDED' ? 'background_interrupted' : 'invalid_session'
  if (Number(session.lifecycle_generation || 0) !== context.lifecycleGeneration) return 'background_interrupted'
  if (now - session.last_active_at > PERF_SESSION_MAX_IDLE_MS) return 'expired_start'
  return 'valid'
}

export function recordInvalidMeasurement(metric, validity, meta, now = Date.now()) {
  try {
    const session = readSession()
    if (!session) return false
    appendTimelineEvent(session, 'duration_invalid', { metric, validity, ...(meta || {}) }, now)
    return true
  } catch {
    return false
  }
}

export function consumeStart(name, now = Date.now()) {
  const starts = readStarts()
  const start = starts[name]
  delete starts[name]
  safeSet(STARTS_KEY, starts)

  if (!start) return { validity: 'missing_start', durationMs: null }
  const session = readSession()
  if (!session || session.id !== start.perf_session_id) {
    return { validity: 'invalid_session', durationMs: null, startedAt: start.started_at }
  }
  if (session.state === 'SUSPENDED') {
    return { validity: 'background_interrupted', durationMs: null, startedAt: start.started_at }
  }
  const durationMs = now - start.started_at
  if (durationMs < 0) {
    return { validity: 'invalid_clock', durationMs: null, startedAt: start.started_at }
  }
  if (session.state === 'EXPIRED' || durationMs > PERF_SESSION_MAX_IDLE_MS || now - session.last_active_at > PERF_SESSION_MAX_IDLE_MS) {
    session.state = 'EXPIRED'
    session.expired_at = now
    writeSession(session)
    return { validity: 'expired_start', durationMs, startedAt: start.started_at }
  }
  return {
    validity: 'valid',
    durationMs,
    startedAt: start.started_at,
    endedAt: now,
    perfSessionId: session.id,
  }
}

function scheduleFlush() {
  if (flushTimer) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    flushPending()
  }, FLUSH_DELAY_MS)
}

const getTelemetryClientId = () => {
  let clientId = safeGet('dining_client_id', '')
  if (!clientId) {
    clientId = `dc_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`
    safeSet('dining_client_id', clientId)
  }
  return clientId
}

export function flushPending() {
  if (!pendingBatch.length) return
  const batch = pendingBatch
  pendingBatch = []
  try {
    uni.request({
      url: REPORT_URL,
      method: 'POST',
      data: {
        tenant_id: safeGet('tenant_id', ''),
        client_id: getTelemetryClientId(),
        samples: batch,
      },
      timeout: 8000,
    })
  } catch {
    // Best effort only: no toast, no throw, no retry storm.
  }
}

function readSamples(metric) {
  const raw = safeGet(STORAGE_PREFIX + metric, null)
  return Array.isArray(raw) ? raw : []
}

function writeSamples(metric, samples) {
  safeSet(STORAGE_PREFIX + metric, samples)
}

const buildSampleMeta = (session, meta) => ({
  ...readRuntimeDimensions(),
  network_type: session.network_type || 'unknown',
  launch_type: session.launch_type,
  tenant_id: String(safeGet('tenant_id', '') || '').slice(0, 32),
  perf_session_id: session.id,
  validity: 'valid',
  ...(meta || {}),
})

export function recordSample(metric, durationMs, meta) {
  try {
    if (!metric || !Number.isFinite(durationMs) || durationMs < 0) return false
    const maxDuration = MAX_REASONABLE_DURATION_MS[metric]
    if (maxDuration && durationMs > maxDuration) {
      markEvent('duration_invalid', { metric, validity: 'unreasonable_duration', duration_ms: durationMs })
      return false
    }
    const session = ensureActiveSession()
    const roundedMs = Math.round(durationMs)
    const enrichedMeta = buildSampleMeta(session, meta)
    const samples = readSamples(metric)
    samples.push({ t: Date.now(), ms: roundedMs, meta: enrichedMeta })
    if (samples.length > MAX_SAMPLES) samples.splice(0, samples.length - MAX_SAMPLES)
    writeSamples(metric, samples)
    pendingBatch.push({
      metric,
      ms: roundedMs,
      meta: JSON.stringify(enrichedMeta).slice(0, 500),
    })
    if (pendingBatch.length >= FLUSH_BATCH_SIZE) flushPending()
    else scheduleFlush()
    return true
  } catch {
    return false
  }
}

export function recordDurationFromStart(metric, startName = metric, meta, now = Date.now()) {
  try {
    const result = consumeStart(startName, now)
    if (result.validity !== 'valid') {
      markEvent('duration_invalid', { metric, validity: result.validity }, now)
      return result
    }
    const maxDuration = MAX_REASONABLE_DURATION_MS[metric]
    if (maxDuration && result.durationMs > maxDuration) {
      const invalid = { ...result, validity: 'unreasonable_duration' }
      markEvent('duration_invalid', { metric, validity: invalid.validity, duration_ms: result.durationMs }, now)
      return invalid
    }
    recordSample(metric, result.durationMs, {
      ...(meta || {}),
      validity: 'valid',
    })
    return result
  } catch {
    return { validity: 'telemetry_error', durationMs: null }
  }
}

function percentile(sortedMs, p) {
  if (!sortedMs.length) return 0
  const idx = Math.min(sortedMs.length - 1, Math.ceil((p / 100) * sortedMs.length) - 1)
  return sortedMs[Math.max(0, idx)]
}

export function getMetricSamples(metric) {
  return readSamples(metric)
}

export function getTimeline(sessionId) {
  const id = sessionId || readSession()?.id
  return id ? readTimelineFor(id) : []
}

export function getStats(metric) {
  const samples = readSamples(metric).filter((sample) => (
    sample?.meta?.validity !== 'invalid'
    && (!['entry_resolve', 'menu_api', 'shop_info_api', 'submit_order'].includes(metric) || !sample?.meta?.status || sample.meta.status === 'success')
  ))
  const sorted = samples.map((sample) => sample.ms).sort((a, b) => a - b)
  if (!sorted.length) return { metric, count: 0, avg: 0, p50: 0, p95: 0, min: 0, max: 0 }
  const sum = sorted.reduce((a, b) => a + b, 0)
  return {
    metric,
    count: sorted.length,
    avg: Math.round(sum / sorted.length),
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    min: sorted[0],
    max: sorted[sorted.length - 1],
  }
}

export function getAllStats() {
  return TRACKED_METRICS.map(getStats)
}

export function clearAll() {
  TRACKED_METRICS.forEach((metric) => safeRemove(STORAGE_PREFIX + metric))
  safeRemove(STARTS_KEY)
  const timelineIds = safeGet(TIMELINE_INDEX_KEY, [])
  if (Array.isArray(timelineIds)) timelineIds.forEach((id) => safeRemove(TIMELINE_PREFIX + id))
  safeRemove(TIMELINE_INDEX_KEY)
  safeRemove(SESSION_KEY)
}
