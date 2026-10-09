import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const dialog = readFileSync(new URL('../src/components/super/SuperStepUpDialog.vue', import.meta.url), 'utf8')

function extractFunction(source, name) {
  const marker = `function ${name}(`
  const start = source.indexOf(marker)
  assert.notEqual(start, -1, `${name} must exist in production component code`)
  const bodyStart = source.indexOf('{', start)
  let depth = 0
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1
    if (source[index] === '}') depth -= 1
    if (depth === 0) {
      return Function(`"use strict"; return (${source.slice(start, index + 1)})`)()
    }
  }
  assert.fail(`unable to read ${name} from production component code`)
}

const clearStepUpSensitiveState = extractFunction(dialog, 'clearSensitiveState')
const clearPayConfigSecrets = extractFunction(superAdmin, 'clearPayConfigSecrets')

const stepUpState = {
  totpCode: 'synthetic-totp',
  reason: 'synthetic reason',
  confirmed: true,
  emergency: true,
  emergencyPassword: 'synthetic-password',
  emergencyConfirmation: 'synthetic-confirmation',
}
clearStepUpSensitiveState(stepUpState)
assert.equal(stepUpState.totpCode, '', 'cancel/close must immediately clear TOTP state')
assert.equal(stepUpState.emergencyPassword, '', 'cancel/close must immediately clear emergency password state')
assert.equal(stepUpState.emergencyConfirmation, '', 'cancel/close must clear emergency confirmation state')
clearStepUpSensitiveState(stepUpState)
assert.equal(stepUpState.totpCode, '', 'repeated close must be idempotent')

const payConfigState = {
  wx_api_key_v3: 'synthetic-api-v3-key',
  wx_private_key: 'synthetic-private-key',
  receiver_name: 'Synthetic Merchant',
}
clearPayConfigSecrets(payConfigState)
assert.equal(payConfigState.wx_api_key_v3, '', 'closing payment config must clear APIv3 Key state')
assert.equal(payConfigState.wx_private_key, '', 'closing payment config must clear private key state')
assert.equal(payConfigState.receiver_name, 'Synthetic Merchant', 'non-secret form state must remain compatible')

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
assert.match(dialog, /if \(!open\) clearSensitiveState\(\)/)
assert.match(dialog, /onBeforeUnmount\(clearSensitiveState\)/)
assert.match(dialog, /function handleCancel\(\)[\s\S]*clearSensitiveState\(\)[\s\S]*emit\('cancel'\)/)

assert.match(superAdmin, /function closePayConfig\(\)[\s\S]*clearPayConfigSecrets\(\)/)
assert.match(superAdmin, /onBeforeUnmount\([\s\S]*clearPayConfigSecrets\(\)/)
assert.match(superAdmin, /payConfigSessionId/)
assert.match(superAdmin, /isPayConfigSessionCurrent/)

console.log('Super WxPay secret hardening UI contracts: passed')
