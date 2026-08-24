// Phase-03B acceptance suite: Dashboard state truthfulness.
//
// Locks the five scenarios required by
// docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03B_DASHBOARD_MIGRATION.md. No Vue render
// framework exists in this repo (see test-dashboard-actionable-state.mjs precedent), so
// this combines static source assertions on the real files with small local mirrors of
// the branching logic, exactly like the existing Dashboard test does.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// Normalize CRLF -> LF up front: the real source files are CRLF on this repo/OS, and
// slicing on '\n'-based delimiters below must not silently widen its match window
// (and swallow unrelated later functions) just because the file uses \r\n.
const dashboardSource = fs.readFileSync(path.join(root, 'src/views/Dashboard.vue'), 'utf8').replace(/\r\n/g, '\n')
const statCardSource = fs.readFileSync(path.join(root, 'src/components/StatCard.vue'), 'utf8').replace(/\r\n/g, '\n')

const failures = []
function test(name, fn) {
  try {
    fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}

test('1. Dashboard stats request failure resolves to Error, never a fabricated zero success', () => {
  assert.ok(
    dashboardSource.includes("if (r?.code !== 200 || !r.data) throw new Error(r?.msg || 'dashboard stats unavailable')"),
    'a non-200 or malformed dashboard-stats response must be rejected, not normalized into zeroed overview data',
  )
  const loadStats = dashboardSource.split('async function loadStats(pollMeta = {}) {', 2)[1].split('async function onPullRefresh', 1)[0]
  assert.ok(loadStats.includes('} catch (e) {\n    statsError.value = true'), 'loadStats catch must set statsError, not silently swallow the failure')
  assert.ok(
    loadStats.indexOf('statsError.value = true') > loadStats.indexOf('} catch'),
    'statsError must only become true inside the catch branch, never on the success path',
  )
  // StatCard itself must render loading, THEN error, THEN data -- mutually exclusive,
  // so a failed fetch can never fall through to the a-statistic showing 0.
  const loadingIdx = statCardSource.indexOf('v-if="loading"')
  const errorIdx = statCardSource.indexOf('v-else-if="error"')
  const dataIdx = statCardSource.indexOf('<template v-else>')
  assert.ok(loadingIdx !== -1 && errorIdx !== -1 && dataIdx !== -1, 'StatCard must have distinct loading/error/data branches')
  assert.ok(loadingIdx < errorIdx && errorIdx < dataIdx, 'StatCard must evaluate loading, then error, before ever rendering the numeric value')
  assert.ok(
    dashboardSource.includes(':error="statsError"') && dashboardSource.includes('error-text="数据加载失败，请检查网络"'),
    'the revenue StatCard must be wired to the real statsError flag with an explicit failure message, not a placeholder',
  )
})

test('2. Dashboard stats success renders the real reported values, including a genuine zero', () => {
  const loadStats = dashboardSource.split('async function loadStats(pollMeta = {}) {', 2)[1].split('async function onPullRefresh', 1)[0]
  const successBranch = loadStats.split('getDashboardStats().then(r => {', 2)[1].split('}),\n      loadOrders(pollMeta)', 1)[0]
  assert.ok(successBranch.includes('todayRevenue: d.today_revenue || 0'), 'revenue must come from the real response payload, defaulting only a missing field to 0, not standing in for a failure')
  assert.ok(successBranch.indexOf("if (r?.code !== 200") < successBranch.indexOf('todayRevenue: d.today_revenue'), 'the business-code guard must run before any field is read from the response')
})

test('3. A real zero-activity day is not mistaken for a request failure', () => {
  const loadStats = dashboardSource.split('async function loadStats(pollMeta = {}) {', 2)[1].split('async function onPullRefresh', 1)[0]
  assert.ok(loadStats.includes('statsError.value = false'), 'a successful Promise.all resolution (even with all-zero figures) must explicitly clear statsError')
  const successIdx = loadStats.indexOf('statsError.value = false')
  const catchIdx = loadStats.indexOf('} catch (e) {')
  assert.ok(successIdx !== -1 && catchIdx !== -1 && successIdx < catchIdx, 'statsError must be cleared on the success path, ahead of the catch branch textually')
})

test('4. A secondary module (marketing) failure produces its own local error state, not a global fake success', () => {
  const loadMarketing = dashboardSource.split('async function loadMarketingPreview() {', 2)[1].split('async function enableMarketing', 1)[0]
  const loadStats = dashboardSource.split('async function loadStats(pollMeta = {}) {', 2)[1].split('async function onPullRefresh', 1)[0]
  assert.ok(loadMarketing.includes('marketingError.value = true'), 'marketing load failure must set its own error flag')
  assert.ok(!loadMarketing.includes('statsError.value'), 'a marketing failure must not touch statsError -- the two data sources must fail independently')
  assert.ok(!loadStats.includes('marketingError.value'), 'a stats failure must not touch marketingError -- independence must hold in both directions')
  assert.ok(dashboardSource.includes('v-if="marketingError"') && dashboardSource.includes('营销状态加载失败'), 'the marketing card must render its own explicit failure message, distinct from the KPI error')
})

test('5. Pull-to-refresh reports success only on a real success, and explicitly reports failure', () => {
  const onPullRefresh = dashboardSource.split('async function onPullRefresh() {', 2)[1].split('\n}\n', 1)[0]
  assert.ok(onPullRefresh.includes('if (statsError.value)'), 'onPullRefresh must branch on the real statsError flag before showing any toast')
  const successIdx = onPullRefresh.indexOf("message.success('已刷新')")
  const errorIdx = onPullRefresh.indexOf('message.error(')
  assert.ok(successIdx !== -1, 'a successful refresh must still confirm success to the merchant')
  assert.ok(errorIdx !== -1, 'a failed refresh must show an explicit failure message, mirroring OrderManage.manualRefresh -- silence is not an acceptable failure state')
  const ifIdx = onPullRefresh.indexOf('if (statsError.value)')
  assert.ok(ifIdx < errorIdx && errorIdx < successIdx, 'the failure branch (statsError true -> error toast) must be checked before the success toast can fire')
})

if (failures.length) {
  console.error(`Phase-03B RED failures: ${failures.length}`)
  process.exit(1)
}

console.log('Phase-03B dashboard state truthfulness: passed')
