import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8')

assert.match(
  source,
  /v-if="order\.canReject"[^>]*@click="rejectOrder\(order\)"/,
  'R06: reject action must use the server can_reject capability',
)
assert.match(
  source,
  /v-if="order\.canCancel"[^>]*@click="cancelPendingPaymentOrder\(order\)"/,
  'R06: cancel action must use the server can_cancel capability',
)
assert.match(source, /canCancel:\s*o\.can_cancel\s*===\s*true/)
assert.match(source, /canReject:\s*o\.can_reject\s*===\s*true/)
assert.match(source, /refundRequired:\s*o\.refund_required\s*===\s*true/)
assert.match(
  source,
  /v-if="order\.refundRequired"[^>]*>需要退款处理</,
  'R07: terminal paid orders must remain visibly actionable to the owner',
)
assert.doesNotMatch(source, /系统不自动退款/)
assert.doesNotMatch(source, /微信商户平台/)
assert.doesNotMatch(source, /确认已退款/)

console.log('P0_09_ADMIN_PAID_ACTIONS=SERVER_CAPABILITY')
console.log('P0_09_ADMIN_REFUND_ATTENTION=VISIBLE')
