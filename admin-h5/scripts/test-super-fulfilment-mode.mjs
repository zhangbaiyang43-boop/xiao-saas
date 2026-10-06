/** Super fulfilment-mode control source contracts. Authored for CI only. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const control = readFileSync(new URL('../src/views/super/FulfilmentModeControl.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/superFulfilmentMode.js', import.meta.url), 'utf8')

assert.match(superAdmin, /FulfilmentModeControl/)
assert.match(superAdmin, /:mode="detail\.fulfilment_mode"/)
assert.match(superAdmin, /@updated="refreshDetailAfterFulfilmentMode"/)
assert.match(superAdmin, /默认接单方式：自动接单/)

assert.match(control, />自动接单</)
assert.match(control, />手动接单</)
assert.match(control, /适合大多数餐饮门店/)
assert.match(control, /适合需要人工确认库存、产能或订单的门店/)
assert.match(control, /调整原因/)
assert.match(control, /请先填写调整原因/)
assert.match(control, /后续新订单无需人工点击接单/)
assert.match(control, /后续新订单将进入待接单/)
assert.match(control, /不会修改历史订单/)
assert.match(control, /window\.confirm/)
assert.doesNotMatch(control, />\s*PRINT_FIRST\s*</)
assert.doesNotMatch(control, />\s*WORKBENCH\s*</)

assert.match(api, /import superRequest from '\.\/superRequest'/)
assert.match(api, /fulfilment-mode/)
assert.match(api, /'X-Super-Token'/)
assert.match(api, /\{ mode, reason:/)
assert.doesNotMatch(api, /import axios from/)

console.log('TEST-FE superFulfilmentMode: passed')

