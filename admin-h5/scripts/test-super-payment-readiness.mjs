/** Read-only Merchant 360 payment-readiness contracts. Authored for CI execution. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const panel = readFileSync(new URL('../src/views/super/PaymentReadinessPanel.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/superPaymentReadiness.js', import.meta.url), 'utf8')

assert.match(superAdmin, /Merchant 360 · 经营设置 \/ 收款/)
assert.match(superAdmin, /PaymentReadinessPanel/)
assert.match(superAdmin, /:tenant-id="m\.tenant_id"/)
assert.match(superAdmin, /:super-token="superToken"/)
assert.match(superAdmin, /v-model="payConfigForm\.wx_api_key_v3"/)
assert.match(superAdmin, /暂停支付/)

for (const text of ['微信在线收款概况', '顾客付款时机', '微信收款配置摘要', '配置检查清单']) {
  assert.match(panel, new RegExp(text))
}
for (const text of ['未启用', '配置不完整', '配置异常', '尚未完成实时验证', '已验证可收款']) {
  assert.match(panel, new RegExp(text))
}
assert.match(panel, /本页原有收款配置入口仍保留/)
assert.match(panel, /体检区只读/)
assert.match(panel, /重新检查/)
assert.match(panel, /@media \(max-width: 640px\)/)
assert.match(panel, /grid-template-columns:\s*1fr/)
assert.doesNotMatch(panel, /v-model/)
assert.doesNotMatch(panel, /wx_api_key_v3|wx_private_key|WECHAT_APP_SECRET|SECRET_ENCRYPTION_KEY/)
assert.doesNotMatch(panel, /\.post\(|\.patch\(|复制密钥|保存配置|暂停支付|启用支付/)

assert.match(api, /import superRequest from '\.\/superRequest'/)
assert.doesNotMatch(api, /[`'"]\/api\/super\//)

const getCalls = []
globalThis.__superPaymentRequest = {
  get: (...args) => {
    getCalls.push(args)
    return args
  },
}
const executableApi = api.replace(
  "import superRequest from './superRequest'",
  'const superRequest = globalThis.__superPaymentRequest',
)
const executableApiUrl = `data:text/javascript;base64,${Buffer.from(executableApi).toString('base64')}`
const { getSuperPaymentReadiness } = await import(executableApiUrl)

await getSuperPaymentReadiness('super-token', 'tenant/with slash')
assert.equal(getCalls.length, 1)
assert.deepEqual(getCalls[0], [
  '/super/merchants/tenant%2Fwith%20slash/payment-readiness',
  { headers: { 'X-Super-Token': 'super-token' } },
])

console.log('TEST-FE superPaymentReadiness: passed')
