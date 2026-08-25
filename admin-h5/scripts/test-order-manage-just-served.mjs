// OrderManage "just served" feedback: 出餐完成/确认已上菜成功后，商家能立刻知道
// "刚才处理的是哪一单"，而不需要在按等待时长排序的"已上餐"队列里自己找。
// 排序本身（FIFO，等待越久越靠前）不属于本次改动范围，不在此重复验证——
// 见 test-order-list-sort.mjs。
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const src = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8').replace(/\r\n/g, '\n')

const failures = []
function test(name, fn) {
  try {
    fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}

function slice(startMarker, endMarker) {
  const rest = src.split(startMarker, 2)[1]
  if (rest == null) throw new Error(`marker not found: ${startMarker}`)
  return endMarker ? rest.split(endMarker, 1)[0] : rest
}

test('1. justServed state is a separate map, not a reuse of isHighlighted', () => {
  assert.ok(/const\s+justServedMap\s*=\s*ref\(new Map\(\)\)/.test(src), 'justServedMap must exist as its own ref')
  const finishOrderFn = slice('async function finishOrder(order) {', '\nfunction orderNeedsServe')
  assert.ok(!finishOrderFn.includes('isHighlighted('), 'finishOrder must not call into the new-order isHighlighted authority')
})

test('2. finishOrder marks the order as just-served and gives a specific success toast', () => {
  const finishOrderFn = slice('async function finishOrder(order) {', '\nfunction orderNeedsServe')
  assert.ok(finishOrderFn.includes("markJustServed(order.id, '刚出餐')"), 'finishOrder must record a just-served marker')
  assert.ok(/message\.success\(`桌\$\{order\.table\} 已出餐：\$\{orderDishSummary\(order\)\}`\)/.test(finishOrderFn), 'success toast must name the table and dishes, not a generic string')
})

test('3. confirmServed marks the order as just-served and gives a specific success toast', () => {
  const confirmServedFn = slice('async function confirmServed(order) {', '\n\nasync function ')
  assert.ok(confirmServedFn.includes("markJustServed(order.id, '刚上菜')"), 'confirmServed must record a just-served marker')
  assert.ok(/message\.success\(`桌\$\{order\.table\} 已上菜：\$\{orderDishSummary\(order\)\}`\)/.test(confirmServedFn), 'success toast must name the table and dishes, not a generic string')
})

test('4. just-served marker auto-expires on its own timer, independent of workbenchSyncCore highlight expiry', () => {
  const markFn = slice('function markJustServed(orderId, label) {', '\nfunction justServedLabel')
  assert.ok(/setTimeout\(/.test(markFn), 'markJustServed must schedule its own expiry')
  assert.ok(!/highlight/i.test(markFn), 'must not reuse or reference the isHighlighted/workbenchSyncCore highlight vocabulary -- this is a distinct, unrelated signal')
})

test('5. sort order contract (FIFO for pending/preparing/done) is untouched by this change', () => {
  assert.ok(!/orderListSort\.js/.test(src) || fs.readFileSync(path.join(root, 'src/utils/orderListSort.js'), 'utf8').includes("Set(['pending', 'preparing', 'done'])"), 'ACTIVE_ASC_STATUSES must still include done -- this change must not flip the checkout-queue FIFO order')
})

test('6. the just-served tag renders in both the list card and the table-detail drawer row, using the file\'s own existing green vocabulary (not a new token)', () => {
  const matches = src.match(/justServedLabel\(order\.id\)/g) || []
  assert.ok(matches.length >= 4, `expected justServedLabel(order.id) to appear in both the v-if guard and the {{ }} interpolation in at least 2 render locations (>=4 occurrences), found ${matches.length}`)
  assert.ok(src.includes('background:#ecfdf5;color:#047857;border-color:#a7f3d0'), 'must reuse the file\'s existing green tag palette (already used for the "待上菜" tag), not introduce a new color')
})

console.log(`Order-manage just-served feedback: ${failures.length === 0 ? 'passed' : 'FAILED'}`)
if (failures.length > 0) process.exit(1)
