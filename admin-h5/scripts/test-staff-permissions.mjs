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
  'order.serve',
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
assert.equal(can(['*'], 'order.serve'), true)

assert.equal(can([...FRONTDESK], 'pickup.assign'), true)
assert.equal(can([...FRONTDESK], 'order.serve'), false)
assert.equal(can([...FRONTDESK], 'order.accept'), false)

assert.equal(can([...WAITER], 'order.serve'), true)
assert.equal(can([...WAITER], 'order.accept'), false)
assert.equal(can([...WAITER], 'pickup.assign'), false)
assert.equal(can([...WAITER], 'order.complete'), false)

assert.equal(can([...KITCHEN], 'order.accept'), true)
assert.equal(can([...KITCHEN], 'order.complete'), true)
assert.equal(can([...KITCHEN], 'order.serve'), false)
assert.equal(can([...KITCHEN], 'pickup.assign'), false)

console.log('TEST-FE staffPermissions: passed')
