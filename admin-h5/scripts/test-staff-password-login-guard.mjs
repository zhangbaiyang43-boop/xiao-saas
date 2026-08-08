/**
 * Guards: /login/staff must only be called with complete shop_phone+username+password.
 * Auto paths (device / wechat / init) must not reference staffLogin.
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

// TEST: API guard rejects incomplete body (source-level contract)
assert(api.includes("err.code = 'STAFF_LOGIN_INCOMPLETE'"), 'staffLogin must reject incomplete body')
assert(
  api.includes("request.post('/v1/login/staff', { shop_phone, username, password })"),
  'staffLogin must send exact backend fields',
)

// TEST: only Login.vue imports/calls staffLogin among these modules
assert(login.includes('staffLogin'), 'Login.vue must use staffLogin')
assert(!auth.includes('staffLogin'), 'auth store must not call staffLogin')
assert(!device.includes('staffLogin'), 'deviceAuth must not call staffLogin')
assert(auth.includes('staffDeviceLogin'), 'device refresh uses staffDeviceLogin only')

// TEST: handleStaffLogin validates fields before request
assert(login.includes("请输入员工账号"), 'empty username message')
assert(login.includes("请输入密码"), 'empty password message')
assert(login.includes('staffLogin({ shop_phone, username, password })'), 'explicit body fields')

// TEST: onMounted auto path must not call staffLogin
const mountedStart = login.indexOf('onMounted(async')
const mountedEnd = login.indexOf('onBeforeUnmount(clearCountdown)')
assert(mountedStart >= 0 && mountedEnd > mountedStart, 'onMounted block markers')
const onMountedBlock = login.slice(mountedStart, mountedEnd)
assert(!onMountedBlock.includes('staffLogin'), 'onMounted must not call staffLogin')
assert(onMountedBlock.includes('ensureSession'), 'auto path uses ensureSession (device)')
assert(onMountedBlock.includes('finishWechatLogin'), 'oauth sid path uses wechat login')

// TEST: wechat handlers must not call staffLogin
assert(!login.includes('staffLogin(staffForm'), 'must not pass raw form blindly')
const wechatFn = login.slice(login.indexOf('const handleWechatLogin'), mountedStart)
assert(!wechatFn.includes('staffLogin('), 'wechat login must not call staffLogin')

console.log('TEST-FE staffPasswordLoginGuard: passed')
