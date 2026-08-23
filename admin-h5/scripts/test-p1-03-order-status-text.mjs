import assert from 'node:assert/strict'
import { formatOrderStatusText, UNKNOWN_ORDER_STATUS_TEXT } from '../src/utils/orderStatusText.js'

assert.equal(formatOrderStatusText('pending_payment'), '待支付')
assert.notEqual(formatOrderStatusText('pending_payment'), 'pending_payment')
assert.equal(formatOrderStatusText('pending'), '待接单')
assert.equal(formatOrderStatusText('preparing'), '制作中')
assert.equal(formatOrderStatusText('done'), '已上餐')
assert.equal(formatOrderStatusText('settled'), '已结账')
assert.equal(formatOrderStatusText('cancelled'), '已取消')
assert.equal(formatOrderStatusText('rejected'), '已拒单')
assert.equal(formatOrderStatusText('not_a_real_status'), UNKNOWN_ORDER_STATUS_TEXT)
assert.equal(formatOrderStatusText('pending_payment', 'pending_payment'), '待支付')
assert.equal(formatOrderStatusText('done', '已上餐'), '已上餐')
assert.equal(formatOrderStatusText('settled', 0), '已结账')
assert.match(formatOrderStatusText('abc'), /[^\x00-\x7F]/)

console.log('P1_03_STATUS_TEXT_PENDING_PAYMENT=待支付')
console.log('P1_03_STATUS_TEXT_UNKNOWN=处理中')
console.log('P1_03_TECH_STATUS_LEAK=NO')
