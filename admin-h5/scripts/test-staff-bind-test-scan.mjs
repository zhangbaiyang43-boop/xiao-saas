/**
 * Phase 1: StaffManage no longer exposes TEMP/formal bind QR as product UI.
 * TEMP scanner helpers may remain in the repo for a later cleanup phase.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = path.resolve(root, '..')
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8')
const assert = (cond, msg) => {
  if (!cond) throw new Error(msg)
}

const staffManage = read('src/views/StaffManage.vue')
const api = read('src/api/index.js')

assert(!staffManage.includes('TEMP_STAFF_SCAN_TEST'), 'StaffManage exited TEMP scan UI')
assert(!staffManage.includes('test_scan_payload'), 'StaffManage exited test QR payload UI')
assert(!staffManage.includes('createMiniprogramBindSession'), 'StaffManage exited bind session UI')
assert(!staffManage.includes('生成微信绑定码'), 'WeChat bind CTA removed')
assert(api.includes('createMiniprogramBindSession'), 'bind session API retained for later cleanup')

const scannerPath = path.join(repoRoot, 'member-mini-client/src/utils/staffBindTestScanner.js')
assert(fs.existsSync(scannerPath), 'TEMP scanner file retained (cleanup later)')

console.log('TEST-FE staffBindTestScan: passed (UI exited, helpers retained)')
