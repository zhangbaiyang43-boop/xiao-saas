import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const dialog = readFileSync(new URL('../src/components/super/SuperStepUpDialog.vue', import.meta.url), 'utf8')

assert.match(superAdmin, /SuperStepUpDialog/)
assert.match(superAdmin, /WXPAY_SECRET_COPY_DISABLED/)
assert.match(superAdmin, /跨商户复制已停用/)
assert.match(superAdmin, /配置已保存并暂停，请重新验证后开启/)
assert.match(superAdmin, /delete payload\.wx_api_key_v3/)
assert.match(superAdmin, /delete payload\.wx_private_key/)
assert.match(superAdmin, /reason: stepUp\.reason/)
assert.match(superAdmin, /totp_code: stepUp\.totpCode/)
assert.match(superAdmin, /emergency_password: stepUp\.emergencyPassword/)
assert.match(superAdmin, /emergency_confirmation: stepUp\.emergencyConfirmation/)
assert.doesNotMatch(superAdmin, /window\.prompt\(/)

assert.match(dialog, /a-modal/)
assert.match(dialog, /动态口令/)
assert.match(dialog, /操作原因/)
assert.match(dialog, /紧急暂停/)
assert.match(dialog, /type="password"/)
assert.match(dialog, /390px/)
assert.doesNotMatch(dialog, /localStorage|sessionStorage/)

console.log('Super WxPay secret hardening UI contracts: passed')
