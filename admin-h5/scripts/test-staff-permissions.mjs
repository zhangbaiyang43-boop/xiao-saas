/**
 * Mirror backend Role → Permission matrix for admin-h5 can() expectations.
 */
import assert from 'node:assert/strict'

const FRONTDESK = new Set([
  'order.view_fulfillment',
  'table.view',
  'pickup.view',
  'pickup.assign',
  'pickup.change',
])

const WAITER = new Set([
  'order.view_fulfillment',
  'table.view',
  'pickup.view',
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

assert.equal(can([...FRONTDESK], 'pickup.assign'), true)
assert.equal(can([...FRONTDESK], 'pickup.change'), true)
assert.equal(can([...FRONTDESK], 'order.accept'), false)
assert.equal(can([...FRONTDESK], 'order.complete'), false)
assert.equal(can([...FRONTDESK], 'kitchen.print_reprint'), false)
assert.equal(can([...FRONTDESK], 'finance.settle'), false)

assert.equal(can([...WAITER], 'order.view_fulfillment'), true)
assert.equal(can([...WAITER], 'order.accept'), false)
assert.equal(can([...WAITER], 'pickup.assign'), false)
assert.equal(can([...WAITER], 'pickup.change'), false)
assert.equal(can([...WAITER], 'finance.settle'), false)
assert.equal(can([...WAITER], 'order.complete'), false)

assert.equal(can([...KITCHEN], 'order.accept'), true)
assert.equal(can([...KITCHEN], 'order.complete'), true)
assert.equal(can([...KITCHEN], 'pickup.assign'), false)
assert.equal(can([...KITCHEN], 'staff.manage'), false)

console.log('TEST-FE staffPermissions: passed')
