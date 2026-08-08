/**
 * Guards: /login/staff must only be called with complete shop_phone+username+password.
 * Auto paths (device / init) must not reference staffLogin.
 * 公众号 OAuth must not auto-start from Login.
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

const api = read('src/api/index.js')
const login = read('src/views/Login.vue')
const auth = read('src/stores/auth.js')
const device = read('src/utils/deviceAuth.js')
const router = read('src/router/index.js')
const handoff = read('src/views/StaffHandoff.vue')
const staffManage = read('src/views/StaffManage.vue')

// TEST: API guard rejects incomplete body (source-level contract)
assert(api.includes("err.code = 'STAFF_LOGIN_INCOMPLETE'"), 'staffLogin must reject incomplete body')
assert(
  api.includes("request.post('/v1/login/staff', { shop_phone, username, password })"),
  'staffLogin must send exact backend fields',
)
assert(api.includes("'/v1/login/staff/handoff'"), 'handoff login API exists')
assert(api.includes('createMiniprogramBindSession'), 'miniprogram bind session API exists')

// TEST: only Login.vue imports/calls staffLogin among these modules
assert(login.includes('staffLogin'), 'Login.vue must use staffLogin')
assert(!auth.includes('staffLogin'), 'auth store must not call staffLogin')
assert(!device.includes('staffLogin'), 'deviceAuth must not call staffLogin')
assert(auth.includes('staffDeviceLogin'), 'device refresh uses staffDeviceLogin only')

// TEST: handleStaffLogin validates fields before request
assert(login.includes('请输入员工账号'), 'empty username message')
assert(login.includes('请输入密码'), 'empty password message')
assert(login.includes('staffLogin({ shop_phone, username, password })'), 'explicit body fields')
assert(login.includes('备用账号登录'), 'password fallback remains')
assert(login.includes('开心点单'), 'points staff to mini-program entry')
assert(!login.includes('微信快捷登录'), 'OA wechat quick login button removed')
assert(!login.includes('getStaffWechatOauthStart'), 'Login must not start OA OAuth')
assert(!login.includes('handleWechatLogin'), 'Login must not auto OAuth handler')

// TEST: onMounted auto path must not call staffLogin / OAuth
const mountedStart = login.indexOf('onMounted(async')
const mountedEnd = login.indexOf('onBeforeUnmount(clearCountdown)')
assert(mountedStart >= 0 && mountedEnd > mountedStart, 'onMounted block markers')
const onMountedBlock = login.slice(mountedStart, mountedEnd)
assert(!onMountedBlock.includes('staffLogin'), 'onMounted must not call staffLogin')
assert(onMountedBlock.includes('ensureSession'), 'auto path uses ensureSession (device)')
assert(!onMountedBlock.includes('finishWechatLogin'), 'must not consume OA oauth sid')
assert(!onMountedBlock.includes('oauth/start'), 'must not redirect to OA oauth')

// TEST: StaffHandoff + router
assert(router.includes("path: '/staff-handoff'"), 'staff-handoff route registered')
assert(handoff.includes('staffHandoffLogin'), 'StaffHandoff consumes handoff token')
assert(handoff.includes("replaceState"), 'StaffHandoff clears fragment')
assert(staffManage.includes('createMiniprogramBindSession'), 'StaffManage uses mini-program code')
assert(staffManage.includes('getStaffMiniprogramStatus'), 'StaffManage gates bind UI by feature flag')
assert(staffManage.includes('mpAuthEnabled'), 'StaffManage bind button respects mpAuthEnabled')
assert(staffManage.includes('qrcode_data_url'), 'formal bind uses server wxacode data URL')
// TEMP_STAFF_BIND_TEST_SCAN: local QR for test_scan_payload only (not H5 URL QR primary)
assert(staffManage.includes('TEMP_STAFF_BIND_TEST_SCAN'), 'test scan TEMP marker present')
assert(staffManage.includes('test_scan_payload'), 'test QR gated by API payload')
assert(staffManage.includes('QRCode.toDataURL'), 'test plain QR generated locally with qrcode lib')
assert(api.includes("'/v1/staff/miniprogram/status'"), 'miniprogram status API exists')
assert(read('src/api/request.js').includes("hostname === 'saas.zhangbaiyang.com'"), 'prod H5 uses same-origin /api')
assert(read('src/api/request.js').includes("return '/api'"), 'prod H5 baseURL is /api')

console.log('TEST-FE staffPasswordLoginGuard: passed')
