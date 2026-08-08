/**
 * Static checks: Cookie mode must not persist device_credential in localStorage.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const deviceAuth = fs.readFileSync(path.join(root, 'src/utils/deviceAuth.js'), 'utf8')
const authStore = fs.readFileSync(path.join(root, 'src/stores/auth.js'), 'utf8')

function assert(cond, msg) {
  if (!cond) throw new Error(msg)
}

assert(deviceAuth.includes('isCookieDeviceMode'), 'missing isCookieDeviceMode')
assert(
  deviceAuth.includes('localStorage.removeItem(DEVICE_CRED_KEY)') &&
    deviceAuth.includes('if (isCookieDeviceMode())'),
  'cookie mode must clear/avoid localStorage device secret',
)
assert(
  /if \(isCookieDeviceMode\(\)\)\s*\{\s*[\s\S]*?localStorage\.removeItem\(DEVICE_CRED_KEY\)/.test(
    deviceAuth,
  ) || deviceAuth.includes('// Cookie mode: HttpOnly cookie holds the secret'),
  'cookie mode branch must not setItem device secret',
)
assert(
  !/isCookieDeviceMode\(\)\)[\s\S]{0,80}localStorage\.setItem\(DEVICE_CRED_KEY/.test(deviceAuth),
  'cookie mode must not localStorage.setItem device credential',
)
assert(authStore.includes('isCookieDeviceMode'), 'auth store must respect cookie mode')
assert(
  authStore.includes('clearDeviceCredential()') &&
    authStore.includes('if (isCookieDeviceMode())'),
  'applySession must clear credential in cookie mode',
)
assert(
  authStore.includes('staffDeviceLogin(payload)') || authStore.includes('staffDeviceLogin({'),
  'device refresh must call staffDeviceLogin',
)

// Phase 2 Final Gate: logout → logout-device → clearAuth; must not ensureSession restore.
const logoutBlock = authStore.match(/async function logoutCurrentDevice\(\) \{[\s\S]*?\n  \}/)?.[0] || ''
assert(logoutBlock, 'missing logoutCurrentDevice')
assert(logoutBlock.includes('staffLogoutDevice'), 'logout must call staffLogoutDevice')
assert(logoutBlock.includes('clearAuth()'), 'logout must clearAuth after logout-device')
assert(!logoutBlock.includes('ensureSession'), 'logout must not call ensureSession')

console.log('TEST-FE staffDeviceCookie: passed')
