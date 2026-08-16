
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import request, {
  classifyRequestFailure,
  matchApiMetric,
  readProcessTimeMs,
} from '@/api/request'
import {
  PERF_SESSION_MAX_IDLE_MS,
  discardStart,
  flushPending,
  getMetricSamples,
  getPerformanceSession,
  getStats,
  getTimeline,
  handleAppHide,
  handleAppShow,
  markEventOnce,
  markStart,
  recordSample,
  recordDurationFromStart,
  startPerformanceSession,
} from '@/utils/perf'

const BASE_TIME = 1_800_000_000_000
const MENU_SOURCE = readFileSync(fileURLToPath(new URL('../../subpkg-order/pages/menu.vue', import.meta.url)), 'utf8')

const installRequestMock = (handler) => {
  uni.request = vi.fn(handler)
}

describe('performance session timeline', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(BASE_TIME)
    uni.getAccountInfoSync = vi.fn(() => ({ miniProgram: { version: '1.2.3', envVersion: 'develop' } }))
    uni.getSystemInfoSync = vi.fn(() => ({ platform: 'devtools' }))
    uni.getNetworkType = vi.fn(({ success }) => success?.({ networkType: 'wifi' }))
    installRequestMock(() => {})
  })

  it('rejects a 110 second launch mark instead of creating a valid cold latency sample', () => {
    startPerformanceSession('cold')
    markStart('launch_to_entry')

    vi.setSystemTime(BASE_TIME + 110_000)
    const result = recordDurationFromStart('launch_to_entry', 'launch_to_entry')

    expect(PERF_SESSION_MAX_IDLE_MS).toBeLessThan(110_000)
    expect(result.validity).toBe('expired_start')
    expect(getMetricSamples('launch_to_entry')).toHaveLength(0)
  })

  it('starts a warm session after a long background and does not reuse interrupted starts', () => {
    const cold = startPerformanceSession('cold')
    markStart('entry_to_menu')
    handleAppHide(BASE_TIME + 1_000)

    const warm = handleAppShow(BASE_TIME + PERF_SESSION_MAX_IDLE_MS + 2_000)
    const result = recordDurationFromStart('entry_to_menu', 'entry_to_menu')

    expect(warm.id).not.toBe(cold.id)
    expect(warm.launch_type).toBe('warm')
    expect(result.validity).toBe('missing_start')
    expect(getMetricSamples('entry_to_menu')).toHaveLength(0)
  })

  it('keeps a normal cold flow ordered under one performance session id', () => {
    const session = startPerformanceSession('cold')
    const events = [
      'app_launch',
      'entry_onload',
      'entry_resolve_start',
      'entry_resolve_success',
      'menu_onload',
      'menu_api_start',
      'menu_api_success',
      'menu_data_processed',
      'first_content',
      'interactive',
    ]

    events.forEach((event, index) => {
      vi.setSystemTime(BASE_TIME + index * 10)
      markEventOnce(event, event)
    })

    const timeline = getTimeline()
    expect(timeline.map((item) => item.event)).toEqual(events)
    expect(new Set(timeline.map((item) => item.perf_session_id))).toEqual(new Set([session.id]))
    expect(getPerformanceSession().launch_type).toBe('cold')
  })

  it('records first_content and interactive only once per page guard', () => {
    startPerformanceSession('cold')

    expect(markEventOnce('first_content', 'menu:first_content')).toBe(true)
    expect(markEventOnce('first_content', 'menu:first_content')).toBe(false)
    expect(markEventOnce('interactive', 'menu:interactive')).toBe(true)
    expect(markEventOnce('interactive', 'menu:interactive')).toBe(false)

    expect(getTimeline().filter((item) => item.event === 'first_content')).toHaveLength(1)
    expect(getTimeline().filter((item) => item.event === 'interactive')).toHaveLength(1)
  })

  it('binds first-content selectors to the DishList component boundary', () => {
    expect(MENU_SOURCE).toContain('<DishList')
    expect(MENU_SOURCE).toContain('ref="dishList"')
    expect(MENU_SOURCE).toContain(".in(page.$refs?.dishList)")
  })

  it('bounds persisted timeline keys to recent performance sessions', () => {
    uni.removeStorageSync.mockClear()
    for (let index = 0; index < 7; index += 1) {
      vi.setSystemTime(BASE_TIME + index)
      startPerformanceSession(index === 0 ? 'cold' : 'warm')
      markEventOnce('app_show', `show:${index}`)
    }

    const removedTimelineKeys = uni.removeStorageSync.mock.calls
      .map(([key]) => key)
      .filter((key) => String(key).startsWith('perf_timeline_'))
    expect(removedTimelineKeys.length).toBeGreaterThanOrEqual(2)
  })

  it('can discard a direct-menu launch mark before a later entry', () => {
    startPerformanceSession('cold')
    markStart('launch_to_entry')
    discardStart('launch_to_entry')

    vi.setSystemTime(BASE_TIME + 20_000)
    expect(recordDurationFromStart('launch_to_entry', 'launch_to_entry').validity).toBe('missing_start')
    expect(getMetricSamples('launch_to_entry')).toHaveLength(0)
  })

  it('keeps failed entry resolve samples out of success latency stats', () => {
    startPerformanceSession('cold')
    recordSample('entry_resolve', 100, { status: 'failure' })
    expect(getMetricSamples('entry_resolve')).toHaveLength(1)
    expect(getStats('entry_resolve').count).toBe(0)
  })
})

describe('request performance sidecar', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(BASE_TIME)
    startPerformanceSession('cold')
  })

  it('records success client, server, and network approximation without changing the payload', async () => {
    installRequestMock(({ success }) => {
      vi.setSystemTime(BASE_TIME + 300)
      success({ statusCode: 200, data: { code: 200, data: { items: [] } }, header: { 'X-Process-Time-Ms': '100' } })
    })

    const response = await request({ url: '/v1/menu/items', method: 'GET' })
    const sample = getMetricSamples('menu_api').at(-1)

    expect(response).toEqual({ code: 200, data: { items: [] } })
    expect(sample.ms).toBe(300)
    expect(sample.meta).toMatchObject({
      api_name: 'menu_items',
      method: 'GET',
      client_ms: 300,
      server_ms: 100,
      network_approx_ms: 200,
      status: 'success',
      http_status: 200,
      error_type: null,
    })
  })

  it('keeps missing, invalid, and negative server headers null', () => {
    expect(readProcessTimeMs({})).toBeNull()
    expect(readProcessTimeMs({ 'X-Process-Time-Ms': 'bad' })).toBeNull()
    expect(readProcessTimeMs({ 'X-Process-Time-Ms': '   ' })).toBeNull()
    expect(readProcessTimeMs({ 'X-Process-Time-Ms': ['100'] })).toBeNull()
    expect(readProcessTimeMs({ 'x-process-time-ms': '-1' })).toBeNull()
    expect(readProcessTimeMs({ 'x-process-time-ms': '0' })).toBe(0)
  })

  it('keeps server and network approximation null when the success header is missing', async () => {
    installRequestMock(({ success }) => {
      vi.setSystemTime(BASE_TIME + 300)
      success({ statusCode: 200, data: { code: 200, data: {} }, header: {} })
    })

    await request({ url: '/v1/menu/items', method: 'GET' })
    expect(getMetricSamples('menu_api').at(-1).meta).toMatchObject({
      client_ms: 300,
      server_ms: null,
      network_approx_ms: null,
      status: 'success',
    })
  })

  it('records an HTTP 500 as failure while preserving rejection semantics', async () => {
    installRequestMock(({ success }) => {
      vi.setSystemTime(BASE_TIME + 80)
      success({ statusCode: 500, data: { code: 500, msg: 'boom' }, header: {} })
    })

    await expect(request({ url: '/v1/menu/items', method: 'GET' })).rejects.toMatchObject({ statusCode: 500 })
    expect(getMetricSamples('menu_api').at(-1).meta).toMatchObject({
      status: 'failure',
      http_status: 500,
      error_type: 'http',
      server_ms: null,
      network_approx_ms: null,
    })
    expect(getStats('menu_api').count).toBe(0)
  })

  it('records timeout and abort only when the runtime exposes those error messages', async () => {
    installRequestMock(({ fail }) => {
      vi.setSystemTime(BASE_TIME + 150)
      fail({ errMsg: 'request:fail timeout' })
    })
    await expect(request({ url: '/v1/menu/items', method: 'GET' })).rejects.toThrow()
    expect(getMetricSamples('menu_api').at(-1).meta).toMatchObject({ status: 'timeout', error_type: 'timeout' })

    vi.setSystemTime(BASE_TIME + 200)
    installRequestMock(({ fail }) => fail({ errMsg: 'request:fail abort' }))
    await expect(request({ url: '/v1/menu/items', method: 'GET' })).rejects.toThrow()
    expect(getMetricSamples('menu_api').at(-1).meta).toMatchObject({ status: 'abort', error_type: 'abort' })
    expect(classifyRequestFailure('request:fail disconnected')).toEqual({ status: 'failure', errorType: 'network' })
  })

  it('explicitly excludes the performance upload endpoint from API instrumentation', () => {
    expect(matchApiMetric('/api/v1/perf/report', 'POST')).toBeNull()
    expect(matchApiMetric('/v1/perf/report', 'POST')).toBeNull()
  })

  it('invalidates an in-flight request that crosses app background without activating a session', async () => {
    let callbacks
    installRequestMock((options) => { callbacks = options })
    const pending = request({ url: '/v1/menu/items', method: 'GET' })

    handleAppHide(BASE_TIME + 10)
    vi.setSystemTime(BASE_TIME + 5_000)
    callbacks.success({ statusCode: 200, data: { code: 200, data: {} }, header: {} })

    await expect(pending).resolves.toEqual({ code: 200, data: {} })
    expect(getMetricSamples('menu_api')).toHaveLength(0)
    expect(getPerformanceSession().state).toBe('SUSPENDED')
  })

  it('starts an unknown session for a monitored request after the active session idles past TTL', async () => {
    const expiredSessionId = getPerformanceSession().id
    vi.setSystemTime(BASE_TIME + PERF_SESSION_MAX_IDLE_MS + 1)
    installRequestMock(({ success }) => {
      vi.setSystemTime(BASE_TIME + PERF_SESSION_MAX_IDLE_MS + 101)
      success({ statusCode: 200, data: { code: 200, data: { orderId: 'o1' } }, header: {} })
    })

    await expect(request({ url: '/v1/orders', method: 'POST' })).resolves.toEqual({
      code: 200,
      data: { orderId: 'o1' },
    })

    expect(getPerformanceSession().id).not.toBe(expiredSessionId)
    expect(getPerformanceSession().launch_type).toBe('unknown')
    expect(getMetricSamples('submit_order').at(-1)).toMatchObject({
      ms: 100,
      meta: { status: 'success' },
    })
  })

  it('keeps the business request successful when telemetry storage and upload fail', async () => {
    uni.setStorageSync.mockImplementation(() => { throw new Error('storage full') })
    installRequestMock(({ success }) => {
      vi.setSystemTime(BASE_TIME + 20)
      success({ statusCode: 200, data: { code: 200, data: { ok: true } }, header: {} })
    })

    await expect(request({ url: '/v1/menu/items', method: 'GET' })).resolves.toEqual({ code: 200, data: { ok: true } })
    expect(() => flushPending()).not.toThrow()
  })
})
