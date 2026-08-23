import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8')

assert.match(source, /tab="当前订单"/)
assert.match(source, /tab="历史订单"/)
assert.match(source, /date_str: 'today'/)
assert.match(source, /date_str: historyDateKey\.value/)
assert.match(source, /page_size: HISTORICAL_PAGE_SIZE/)
assert.match(source, /order_tail: q/)
assert.match(source, /table_no: q/)
assert.doesNotMatch(source, /date_str: 'last7'/)
assert.match(source, /if \(!isLiveToday\.value\) return historicalOrders\.value/)

console.log('P1_02_ADMIN_CENTER_TABS=LIVE_HISTORY')
console.log('P1_02_ADMIN_HISTORICAL_SERVER_PAGE=YES')
