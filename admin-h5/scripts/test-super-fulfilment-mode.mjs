/** Scope-clean Super fulfilment-mode contracts. Authored for CI execution. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const control = readFileSync(new URL('../src/views/super/FulfilmentModeControl.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/superFulfilmentMode.js', import.meta.url), 'utf8')
const superRequest = readFileSync(new URL('../src/api/superRequest.js', import.meta.url), 'utf8')
const apiBaseUrl = readFileSync(new URL('../src/api/apiBaseUrl.js', import.meta.url), 'utf8')

assert.match(superAdmin, /Merchant 360 · 经营设置/)
assert.match(superAdmin, /FulfilmentModeControl/)
assert.match(superAdmin, /:mode="m\.fulfilment_mode"/)
assert.match(superAdmin, /默认接单方式：自动接单/)
assert.match(superAdmin, /fulfilmentModeLabel\(m\.fulfilment_mode\)/)

assert.match(control, />自动接单</)
assert.match(control, />手动接单</)
assert.match(control, /调整原因/)
assert.match(control, /请先填写调整原因/)
assert.match(control, /商户：\$\{merchant\}/)
assert.match(control, /当前接单方式：\$\{currentLabel\.value\}/)
assert.match(control, /目标接单方式：\$\{modeLabel\(nextMode\)\}/)
assert.match(control, /调整原因：\$\{normalizedReason\}/)
assert.match(control, /本次调整只影响后续新订单，不会修改历史订单/)
assert.match(control, /window\.confirm/)
assert.doesNotMatch(control, />\s*PRINT_FIRST\s*</)
assert.doesNotMatch(control, />\s*WORKBENCH\s*</)

assert.match(api, /import superRequest from '\.\/superRequest'/)
assert.doesNotMatch(api, /[`'"]\/api\/super\//)

const patchCalls = []
globalThis.__superFulfilmentRequest = {
  patch: (...args) => {
    patchCalls.push(args)
    return args
  },
}
const executableApi = api.replace(
  "import superRequest from './superRequest'",
  'const superRequest = globalThis.__superFulfilmentRequest',
)
const executableApiUrl = `data:text/javascript;base64,${Buffer.from(executableApi).toString('base64')}`
const { updateSuperFulfilmentMode } = await import(executableApiUrl)

await updateSuperFulfilmentMode('super-token', 'tenant/with slash', 'PRINT_FIRST', '  认证原因  ')
assert.equal(patchCalls.length, 1)
const [clientPath, payload, config] = patchCalls[0]
assert.equal(clientPath, '/super/merchants/tenant%2Fwith%20slash/fulfilment-mode')
assert.deepEqual(payload, { mode: 'PRINT_FIRST', reason: '认证原因' })
assert.deepEqual(config, { headers: { 'X-Super-Token': 'super-token' } })

assert.match(superAdmin, /const BASE = '\/super'/)
assert.match(superAdmin, /superRequest\.get\(`\$\{BASE\}\/merchants`/)
assert.match(superRequest, /baseURL:\s*resolveApiBaseURL\(\)/)
assert.match(apiBaseUrl, /return envBaseURL \|\| '\/api'/)
const finalBrowserPath = `/api/${clientPath.replace(/^\//, '')}`
assert.equal(finalBrowserPath, '/api/super/merchants/tenant%2Fwith%20slash/fulfilment-mode')
assert.doesNotMatch(finalBrowserPath, /\/api\/api\//)

console.log('TEST-FE superFulfilmentMode: passed')
