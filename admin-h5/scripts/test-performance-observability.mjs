import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath, URL } from 'node:url'

import {
  classifyAdminApiFailure,
  classifyAdminApiResponse,
  createAdminPerformanceCollector,
  installAdminPerformanceDebugOutlet,
  readResponsePayloadSize,
} from '../src/utils/adminPerformance.js'

const VERSION = 'f7464e83efeab28f9360a9d6149cadae116d2e27'

function createFixture(maxEvents = 200) {
  let timestamp = 1_800_000_000_000
  let clock = 100
  const collector = createAdminPerformanceCollector({
    environment: 'local',
    version: VERSION,
    maxEvents,
    now: () => timestamp,
    clock: () => clock,
    scheduleAfterRender: callback => callback(),
    devLog: () => {},
  })

  return {
    collector,
    advance(ms) {
      timestamp += ms
      clock += ms
    },
  }
}

test('event schema always includes the required Phase 02 fields', () => {
  const { collector, advance } = createFixture()
  collector.beginPageNavigation({ name: 'OrderManage', path: '/orders?status=pending' })
  advance(25)
  collector.completePageNavigation({ name: 'OrderManage', path: '/orders?status=pending' })

  const [event] = collector.getEvents()
  assert.deepEqual(Object.keys(event).sort(), [
    'api_group',
    'data_count',
    'duration',
    'environment',
    'event_name',
    'page',
    'payload_size',
    'request_id',
    'request_name',
    'route',
    'size_source',
    'status',
    'timestamp',
    'version',
    'visit_id',
  ].sort())
  assert.equal(event.event_name, 'admin_page_enter')
  assert.equal(event.route, '/orders')
  assert.equal(event.page, 'OrderManage')
  assert.equal(event.duration, 25)
  assert.equal(event.environment, 'local')
  assert.equal(event.version, VERSION)
})

test('bounded queue evicts oldest events and subscribers can unsubscribe', () => {
  const { collector } = createFixture(3)
  const observed = []
  const unsubscribe = collector.subscribe(event => observed.push(event.event_name))

  for (let index = 0; index < 4; index += 1) {
    collector.recordEvent({
      event_name: 'admin_page_enter',
      route: `/orders/${index}`,
      page: 'OrderManage',
      status: 'success',
    })
  }
  unsubscribe()
  collector.recordEvent({
    event_name: 'admin_page_enter',
    route: '/orders/final',
    page: 'OrderManage',
    status: 'success',
  })

  assert.equal(observed.length, 4)
  assert.equal(collector.getEvents().length, 3)
  assert.equal(collector.getEvents()[0].route, '/orders/2')
})

test('production debug outlet exposes detached read-only queue snapshots', () => {
  const collector = createAdminPerformanceCollector({
    environment: 'production',
    version: VERSION,
    now: () => 1_800_000_000_000,
    clock: () => 100,
    scheduleAfterRender: callback => callback(),
    devLog: () => {},
  })
  collector.recordEvent({
    event_name: 'admin_page_enter',
    route: '/orders',
    page: 'OrderManage',
    status: 'success',
    token: 'must-not-leak',
    cookie: 'must-not-leak',
    request_body: { secret: true },
    response_body: { secret: true },
    user: { phone: 'must-not-leak' },
    merchant: { name: 'must-not-leak' },
  })

  const target = {}
  assert.equal(
    installAdminPerformanceDebugOutlet(target, () => collector.getEvents()),
    true,
  )

  const descriptor = Object.getOwnPropertyDescriptor(target, '__ADMIN_PERF_EVENTS__')
  assert.equal(typeof descriptor.get, 'function')
  assert.equal(descriptor.set, undefined)
  assert.equal(descriptor.enumerable, false)
  assert.equal(descriptor.configurable, false)

  const firstSnapshot = target.__ADMIN_PERF_EVENTS__
  assert.ok(Array.isArray(firstSnapshot))
  assert.equal(firstSnapshot.length, 1)
  assert.equal(firstSnapshot[0].environment, 'production')
  assert.equal(firstSnapshot[0].version, VERSION)

  firstSnapshot[0].page = 'tampered'
  firstSnapshot.push({ event_name: 'tampered' })
  const freshSnapshot = target.__ADMIN_PERF_EVENTS__
  assert.equal(freshSnapshot.length, 1)
  assert.equal(freshSnapshot[0].page, 'OrderManage')

  for (const forbidden of ['token', 'cookie', 'request_body', 'response_body', 'user', 'merchant']) {
    assert.equal(Object.hasOwn(freshSnapshot[0], forbidden), false)
  }
  assert.doesNotMatch(JSON.stringify(freshSnapshot), /must-not-leak/)
})

test('all four target pages emit enter, first content and ready once per visit', () => {
  const pages = [
    ['Dashboard', '/', 'Dashboard'],
    ['OrderManage', '/orders', 'OrderManage'],
    ['MenuManage', '/menu', 'DishManage'],
    ['CustomerList', '/customers', 'MemberManage'],
  ]

  for (const [routeName, path, page] of pages) {
    const { collector, advance } = createFixture()
    collector.beginPageNavigation({ name: routeName, path })
    advance(10)
    collector.completePageNavigation({ name: routeName, path })
    advance(20)
    collector.markPageContentReady({ page, status: 'success', data_count: 5 })
    collector.markPageContentReady({ page, status: 'success', data_count: 5 })

    assert.deepEqual(
      collector.getEvents().map(event => event.event_name),
      ['admin_page_enter', 'admin_first_content_visible', 'admin_page_ready'],
    )
    assert.equal(collector.getEvents()[1].duration, 30)
    assert.equal(collector.getEvents()[1].data_count, 5)
  }
})

test('core API groups emit correlated start and successful end events', () => {
  const cases = [
    ['/v1/orders/123/status?source=page', 'orders'],
    ['/v1/menu/items/456', 'menu'],
    ['/v1/customers/789', 'members'],
    ['/v1/coupon-templates/321', 'marketing'],
    ['/v1/tenant/marketing-preview', 'marketing'],
    ['/v1/stats/marketing-effectiveness?days=30', 'marketing'],
  ]

  for (const [url, apiGroup] of cases) {
    const { collector, advance } = createFixture()
    const trace = collector.startApiRequest({ method: 'get', url })
    assert.ok(trace)
    advance(48)
    collector.finishApiRequest(trace, {
      status: 'success',
      payload_size: 128,
      size_source: 'content_length',
    })

    const [start, end] = collector.getEvents()
    assert.equal(start.event_name, 'admin_api_request_start')
    assert.equal(start.duration, null)
    assert.equal(end.event_name, 'admin_api_request_end')
    assert.equal(start.request_id, end.request_id)
    assert.equal(end.api_group, apiGroup)
    assert.equal(end.duration, 48)
    assert.equal(end.payload_size, 128)
    assert.doesNotMatch(end.request_name, /123|456|789|321|source|days/)
  }
})

test('API response and failure statuses remain distinguishable', () => {
  assert.equal(classifyAdminApiResponse({ success: true, data: {} }), 'success')
  assert.equal(classifyAdminApiResponse({ success: false, message: 'error' }), 'business_error')
  assert.equal(classifyAdminApiResponse({ code: 500, msg: 'error' }), 'business_error')
  assert.equal(classifyAdminApiFailure({ __duplicateSkipped: true }), 'duplicate_skipped')
  assert.equal(classifyAdminApiFailure({ code: 'ERR_CANCELED' }), 'cancelled')
  assert.equal(classifyAdminApiFailure({ code: 'ECONNABORTED' }), 'timeout')
  assert.equal(classifyAdminApiFailure({ response: { status: 503 } }), 'http_error')
  assert.equal(classifyAdminApiFailure({ request: {} }), 'network_error')
})

test('payload size uses Content-Length and marks unavailable values honestly', () => {
  assert.deepEqual(readResponsePayloadSize({ 'content-length': '512' }), {
    payload_size: 512,
    size_source: 'content_length',
  })
  assert.deepEqual(readResponsePayloadSize({ get: key => key === 'content-length' ? '64' : null }), {
    payload_size: 64,
    size_source: 'content_length',
  })
  assert.deepEqual(readResponsePayloadSize({}), {
    payload_size: null,
    size_source: 'unavailable',
  })
})

test('telemetry input failures stay isolated from the business caller', () => {
  const { collector } = createFixture()
  const invalidUrl = { toString() { throw new Error('unreadable url') } }
  assert.doesNotThrow(() => collector.startApiRequest({ method: 'get', url: invalidUrl }))
  assert.equal(collector.startApiRequest({ method: 'get', url: invalidUrl }), null)
  assert.equal(collector.getEvents().length, 0)
})

test('router, request wrapper and target pages use the unified collector', () => {
  const source = relativePath => readFileSync(
    fileURLToPath(new URL(`../${relativePath}`, import.meta.url)),
    'utf8',
  )
  const router = source('src/router/index.js')
  const request = source('src/api/request.js')
  const pageSources = [
    ['src/views/Dashboard.vue', 'Dashboard'],
    ['src/views/OrderManage.vue', 'OrderManage'],
    ['src/views/MenuManage.vue', 'DishManage'],
    ['src/views/CustomerList.vue', 'MemberManage'],
  ]

  assert.match(router, /beginPageNavigation\(to\)/)
  assert.match(router, /completePageNavigation\(to, failure\)/)
  assert.match(request, /startAdminApiRequest\(config\)/)
  assert.match(request, /finishAdminApiRequest\(/)
  for (const [file, page] of pageSources) {
    const pageSource = source(file)
    assert.match(pageSource, new RegExp(`markPageContentReady\\(\\{[\\s\\S]*?page:\\s*['\"]${page}['\"]`))
  }
})

test('collector has no network outlet and build injects actual checkout SHA', () => {
  const perfSource = readFileSync(
    fileURLToPath(new URL('../src/utils/adminPerformance.js', import.meta.url)),
    'utf8',
  )
  const viteSource = readFileSync(
    fileURLToPath(new URL('../vite.config.js', import.meta.url)),
    'utf8',
  )

  assert.doesNotMatch(perfSource, /\b(?:fetch|sendBeacon|XMLHttpRequest)\s*\(/)
  assert.doesNotMatch(perfSource, /\baxios\s*\.\s*post\s*\(/)
  assert.match(viteSource, /execFileSync\(['"]git['"],\s*\[['"]rev-parse['"],\s*['"]HEAD['"]\]/)
  assert.match(viteSource, /__ADMIN_BUILD_VERSION__/)
})

test('project check command includes the observability contract test', () => {
  const pkg = JSON.parse(readFileSync(
    fileURLToPath(new URL('../package.json', import.meta.url)),
    'utf8',
  ))
  assert.equal(pkg.scripts['test:performance-observability'], 'node --test scripts/test-performance-observability.mjs')
  assert.match(pkg.scripts.check, /test:performance-observability/)
})
