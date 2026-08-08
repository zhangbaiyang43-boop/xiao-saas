/**
 * TEMP_STAFF_SCAN_TEST — 正式小程序上线后删除
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8')
const assert = (cond, msg) => {
  if (!cond) throw new Error(msg)
}

const staffManage = read('src/views/StaffManage.vue')
assert(staffManage.includes('TEMP_STAFF_SCAN_TEST'), 'TEMP marker')
assert(staffManage.includes('test_scan_payload'), 'test QR from same-session payload')
assert(staffManage.includes('测试二维码'), 'test QR label')
assert(staffManage.includes('我的 → 扫一扫'), 'points to miniapp scan entry')
assert(staffManage.includes('QRCode.toDataURL'), 'local QR generation')
assert(staffManage.includes('qrcode_data_url'), 'formal wxacode still primary')

console.log('TEST-FE staffBindTestScan: passed')
