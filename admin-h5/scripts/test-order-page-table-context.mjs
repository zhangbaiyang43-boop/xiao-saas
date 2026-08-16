/**
 * P0-01C, Finding C: OrderPage.vue must not fabricate a fake 'A01' table when
 * the route carries no table param, and must fail closed on submit instead of
 * silently ordering under a table nobody scanned.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function read(rel) {
  return fs.readFileSync(path.join(root, rel), 'utf8')
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg)
}

const orderPage = read('src/views/OrderPage.vue')

// case C10: never fabricates a fake table number when one is missing
assert(
  !/route\.query\.table\s*\|\|\s*['"]A01['"]/.test(orderPage),
  'OrderPage.vue must not fall back to a fake A01 table number',
)

// case C09/C12: still reads a real table number when one is provided
assert(
  /const tableNo = computed\(\(\) => route\.query\.table \|\| ''\)/.test(orderPage),
  'OrderPage.vue must read a real route.query.table when present and fall back to empty string, not a fake table',
)

// case C10: submit must fail closed on a missing table, not reach the backend at all
assert(
  /if \(!tableNo\.value\)\s*{\s*showFailToast/.test(orderPage),
  'submitOrder() must fail closed (block submission client-side) when tableNo is empty',
)

// case C11: known backend table-authority rejection should surface through, not
// get swallowed by the generic catch-all
assert(
  orderPage.includes("backendMsg.includes('重新扫码')"),
  'submitOrder() catch block must surface the backend table-authority rejection message when present',
)

console.log('test-order-page-table-context: PASS')
