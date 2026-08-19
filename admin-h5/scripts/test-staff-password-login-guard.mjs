/**
 * Guards: /login/staff must only be called with complete shop_phone+username+password.
 * Auto paths (device / init) must not reference staffLogin.
 * Formal H5 auth: Password + Trusted Device. Staff WeChat/OA/MP/Handoff exited.
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
const staffManage = read('src/views/StaffManage.vue')

assert(api.includes("err.code = 'STAFF_LOGIN_INCOMPLETE'"), 'staffLogin must reject incomplete body')
assert(
  api.includes("request.post('/v1/login/staff', { shop_phone, username, password }"),
  'staffLogin must send exact backend fields',
)
assert(api.includes('withCredentials: true'), 'staffLogin must send credentials for staff_device cookie')
assert(api.includes("'/v1/login/staff/device'"), 'device restore API retained')
assert(api.includes("'/v1/login/staff/logout-device'"), 'logout-device API retained')
assert(!api.includes("'/v1/login/staff/handoff'"), 'handoff login API removed')
assert(!api.includes("'/v1/login/staff/wechat'"), 'OA staff wechat login API removed')
assert(!api.includes('createMiniprogramBindSession'), 'miniprogram bind session API removed')
assert(!api.includes('createWechatBindToken'), 'OA wechat bind token API removed')
assert(!api.includes('unbindStaffWechat'), 'wechat unbind API removed')
assert(!api.includes("'/v1/staff/miniprogram/"), 'miniprogram staff API removed')
assert(!api.includes("'/v1/staff/wechat/"), 'OA staff wechat API removed')

assert(login.includes('staffLogin'), 'Login.vue must use staffLogin')
assert(!auth.includes('staffLogin'), 'auth store must not call staffLogin')
assert(!device.includes('staffLogin'), 'deviceAuth must not call staffLogin')
assert(auth.includes('staffDeviceLogin'), 'device refresh uses staffDeviceLogin only')

assert(login.includes('请输入员工账号'), 'empty username message')
assert(login.includes('请输入密码'), 'empty password message')
assert(login.includes('staffLogin({ shop_phone, username, password })'), 'explicit body fields')
assert(login.includes('员工登录'), 'staff tab formal label')
assert(login.includes('老板登录'), 'owner tab formal label')
assert(!login.includes('备用账号登录'), 'backup copy removed from Login')
assert(!login.includes('员工微信登录'), 'mini-program staff hint removed')
assert(!login.includes('从小程序进入'), 'mini-program entry hint removed')
assert(!login.includes('微信快捷登录'), 'OA wechat quick login button removed')
assert(!login.includes('getStaffWechatOauthStart'), 'Login must not start OA OAuth')
assert(!login.includes('handleWechatLogin'), 'Login must not auto OAuth handler')

const mountedStart = login.indexOf('onMounted(async')
const mountedEnd = login.indexOf('onBeforeUnmount(clearCountdown)')
assert(mountedStart >= 0 && mountedEnd > mountedStart, 'onMounted block markers')
const onMountedBlock = login.slice(mountedStart, mountedEnd)
assert(!onMountedBlock.includes('staffLogin'), 'onMounted must not call staffLogin')
assert(onMountedBlock.includes('ensureSession'), 'auto path uses ensureSession (device)')
assert(!onMountedBlock.includes('finishWechatLogin'), 'must not consume OA oauth sid')
assert(!onMountedBlock.includes('oauth/start'), 'must not redirect to OA oauth')

assert(!router.includes("path: '/staff-handoff'"), 'staff-handoff route removed')
assert(!router.includes("path: '/staff-bind'"), 'staff-bind route removed')
assert(!router.includes('StaffHandoff'), 'StaffHandoff import removed')
assert(!router.includes('StaffBind'), 'StaffBind import removed')
assert(!fs.existsSync(path.join(root, 'src/views/StaffHandoff.vue')), 'StaffHandoff.vue deleted')
assert(!fs.existsSync(path.join(root, 'src/views/StaffBind.vue')), 'StaffBind.vue deleted')

// StaffManage: password primary, WeChat bind UI exited
assert(staffManage.includes('createMerchantAccount'), 'StaffManage creates staff')
assert(staffManage.includes('username'), 'create/edit includes username')
assert(staffManage.includes('password'), 'create/edit includes password')
assert(staffManage.includes('设置登录账号'), 'legacy staff can set login account')
assert(!staffManage.includes('createMiniprogramBindSession'), 'StaffManage exited MP bind UI')
assert(!staffManage.includes('生成微信绑定码'), 'WeChat bind button removed from StaffManage')
assert(!staffManage.includes('正式小程序码'), 'formal wxacode UI removed from StaffManage')
assert(!staffManage.includes('备用账号登录'), 'backup login copy removed from StaffManage')

// F1G-CM-RF: this resolution moved out of request.js into the shared
// apiBaseUrl.js (so the SuperAdmin client can reuse the exact same origin
// authority instead of drifting out of sync) -- request.js now just calls
// resolveApiBaseURL(), verified by test-super-api-origin-authority.mjs.
assert(read('src/api/apiBaseUrl.js').includes("hostname === 'saas.zhangbaiyang.com'"), 'prod H5 uses same-origin /api')
assert(read('src/api/apiBaseUrl.js').includes("return '/api'"), 'prod H5 baseURL is /api')
assert(read('src/api/request.js').includes('resolveApiBaseURL()'), 'request.js must resolve baseURL through the shared authority, not its own copy')

console.log('TEST-FE staffPasswordLoginGuard: passed')
