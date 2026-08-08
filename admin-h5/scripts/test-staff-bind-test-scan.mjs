/**
 * TEMP_STAFF_BIND_TEST_SCAN — Remove after MiniProgram production release verification.
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
assert(staffManage.includes('TEMP_STAFF_BIND_TEST_SCAN'), 'TEMP marker')
assert(staffManage.includes('test_scan_payload'), 'only show test QR when API returns payload')
assert(staffManage.includes('testScanDataUrl'), 'test QR state')
assert(staffManage.includes('QRCode.toDataURL'), 'local QR generation')
assert(staffManage.includes('qrcode_data_url'), 'formal wxacode still primary')
assert(staffManage.includes('开发版测试'), 'dev test label')
assert(staffManage.includes('扫一扫测试'), 'points to miniapp test entry')

console.log('TEST-FE staffBindTestScan: passed')
