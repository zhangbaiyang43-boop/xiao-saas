/**
 * Phase 4B: workbench print-status UI static checks.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function read(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8')
}

const kitchen = read('src/views/KitchenWorkbench.vue')
const waiter = read('src/views/WaiterWorkbench.vue')

assert.ok(kitchen.includes('打印异常'), 'KitchenWorkbench shows print anomaly count')
assert.ok(kitchen.includes('打印失败'), 'KitchenWorkbench shows failed badge')
assert.ok(kitchen.includes('打印状态未知'), 'KitchenWorkbench shows unknown badge')
assert.ok(kitchen.includes('等待桌牌后打印'), 'KitchenWorkbench shows waiting pickup badge')
assert.ok(kitchen.includes('已提交打印'), 'KitchenWorkbench shows SUCCESS label 已提交打印')
assert.ok(kitchen.includes("order.can_reprint"), 'Kitchen reprint gated by can_reprint')
assert.ok(kitchen.includes("reprintOrder"), 'Kitchen still has reprintOrder call')

assert.ok(waiter.includes('打印失败'), 'WaiterWorkbench shows failed badge')
assert.ok(waiter.includes('打印状态未知'), 'WaiterWorkbench shows unknown badge')
assert.ok(!waiter.includes('reprintOrder'), 'WaiterWorkbench must not call reprintOrder')
assert.ok(!waiter.includes('补打'), 'WaiterWorkbench must not show reprint button')

console.log('test-workbench-print-status: ok')
