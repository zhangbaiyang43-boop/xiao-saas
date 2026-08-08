/**
 * TEST-FE：商家桌牌 UI 只消费 can_assign_pickup_no。
 */
import assert from 'node:assert/strict'
import {
  canReplacePickup,
  needsPickup,
  pickupConflictToast,
} from '../src/utils/pickupNoUi.js'

// TEST-FE-01
assert.equal(
  needsPickup({ canAssignPickupNo: true, pickup_no: null }),
  true,
)

// TEST-FE-02
assert.equal(
  needsPickup({ canAssignPickupNo: false, pickup_no: null }),
  false,
)

// TEST-FE-03：unpaid 但后端说可发 → 仍显示
assert.equal(
  needsPickup({
    canAssignPickupNo: true,
    pickup_no: '',
    paymentStatus: 'unpaid',
    status: 'pending',
  }),
  true,
)

// TEST-FE-04：paid 但后端说不可发 → 不显示
assert.equal(
  needsPickup({
    canAssignPickupNo: false,
    pickup_no: null,
    paymentStatus: 'paid',
    status: 'pending',
  }),
  false,
)

// TEST-FE-05
assert.equal(
  needsPickup({ canAssignPickupNo: false, pickup_no: '17' }),
  false,
)
assert.equal(
  canReplacePickup({ pickup_no: '17', status: 'pending' }),
  true,
)
assert.equal(
  canReplacePickup({ pickup_no: '17', status: 'settled' }),
  false,
)

assert.equal(pickupConflictToast('22'), '22号刚被使用，请拿其他桌牌')

console.log('TEST-FE pickupNoUi: passed')
