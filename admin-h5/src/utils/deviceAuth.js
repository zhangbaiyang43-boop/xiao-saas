const DEVICE_CRED_KEY = 'staff_device_credential'
const OAUTH_GUARD_KEY = 'staff_oauth_attempted_at'

/**
 * Cookie mode (default) and JS credential mode are mutually exclusive.
 * VITE_STAFF_DEVICE_COOKIE_ENABLED=false → JS/localStorage mode only.
 * Otherwise Cookie mode: never persist device secret in localStorage.
 */
export function isCookieDeviceMode() {
  const v = import.meta.env.VITE_STAFF_DEVICE_COOKIE_ENABLED
  if (v === 'false' || v === '0') return false
  return true
}

export function isWechatBrowser() {
  return /MicroMessenger/i.test(navigator.userAgent || '')
}

export function saveDeviceCredential(cred) {
  if (isCookieDeviceMode()) {
    // Cookie mode: HttpOnly cookie holds the secret; JS must not store it.
    localStorage.removeItem(DEVICE_CRED_KEY)
    return
  }
  if (cred) localStorage.setItem(DEVICE_CRED_KEY, cred)
  else localStorage.removeItem(DEVICE_CRED_KEY)
}

export function getDeviceCredential() {
  if (isCookieDeviceMode()) return ''
  return localStorage.getItem(DEVICE_CRED_KEY) || ''
}

export function clearDeviceCredential() {
  localStorage.removeItem(DEVICE_CRED_KEY)
}

export function markOauthAttempted() {
  sessionStorage.setItem(OAUTH_GUARD_KEY, String(Date.now()))
}

export function clearOauthAttempted() {
  sessionStorage.removeItem(OAUTH_GUARD_KEY)
}

export function wasOauthAttemptedRecently(ms = 60000) {
  const raw = sessionStorage.getItem(OAUTH_GUARD_KEY)
  if (!raw) return false
  const ts = Number(raw)
  if (!Number.isFinite(ts)) return false
  return Date.now() - ts < ms
}
