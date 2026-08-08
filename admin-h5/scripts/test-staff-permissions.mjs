/**
 * Mirror backend Role → Permission matrix for admin-h5 can() expectations.
 */
import assert from 'node:assert/strict'

const WAITER = new Set([
  'order.view_fulfillment',
  'order.accept',
  'table.view',
  'pickup.view',
  'pickup.assign',
  'pickup.change',
])

const KITCHEN = new Set([
  'kitchen.view',
  'order.view_fulfillment',
  'order.accept',
  'order.complete',
  'kitchen.print_reprint',
  'pickup.view',
])

function can(perms, permission) {
  if (perms.includes('*')) return true
  return perms.includes(permission)
}

assert.equal(can(['*'], 'finance.settle'), true)
assert.equal(can([...WAITER], 'order.accept'), true)
assert.equal(can([...WAITER], 'finance.settle'), false)
assert.equal(can([...WAITER], 'order.complete'), false)
assert.equal(can([...KITCHEN], 'order.complete'), true)
assert.equal(can([...KITCHEN], 'pickup.assign'), false)
assert.equal(can([...KITCHEN], 'staff.manage'), false)

console.log('TEST-FE staffPermissions: passed')
