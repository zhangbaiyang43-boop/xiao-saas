import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const apiSource = fs.readFileSync(path.join(root, 'src/api/index.js'), 'utf8')
const orderSource = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8')

assert.match(
  apiSource,
  /export const refundPaidOrder = \(id\) => request\.post\(`\/v1\/orders\/\$\{id\}\/refund`\)/,
  'must wrap existing POST /v1/orders/{id}/refund',
)

assert.match(orderSource, /refundPaidOrder,/)
assert.match(
  orderSource,
  /v-if="order\.refundRequired"[^>]*@click="refundPaidOrderClick\(order\)"/,
  'refund button must appear on refund_required orders',
)
assert.match(orderSource, /const res = await refundPaidOrder\(order\.id\)/)
assert.match(
  orderSource,
  /if \(res\.code === 200\) message\.success[\s\S]*await reconcileAfterOrderAction\(\)/,
  'successful refund must reload orders from the server',
)
assert.match(orderSource, /await reconcileAfterOrderAction\(\)/)
assert.doesNotMatch(
  orderSource,
  /refund_status\s*=/,
  'must not locally assign refund_status',
)
assert.doesNotMatch(orderSource, /can\(['"]finance\.refund['"]\)/)
assert.doesNotMatch(orderSource, /系统不自动退款/)
assert.doesNotMatch(orderSource, /微信商户平台/)

console.log('P0_REFUND_EXPOSURE_API=WRAPPED')
console.log('P0_REFUND_EXPOSURE_BUTTON=VISIBLE')
console.log('P0_REFUND_EXPOSURE_REFRESH=SERVER')
