// TEMP_STAFF_BIND_TEST_SCAN
// Remove after MiniProgram production release verification.
// Test entry only transports scene into existing staff-bind; never skips wx.login / code2session.

export const STAFF_MP_TEST_SCAN_PREFIX = 'KXD_STAFF_BIND_V1:'
export const STAFF_MP_SCENE_HEX_RE = /^[0-9a-fA-F]{32}$/

/** Official wxacode + navigateTo query → one normalized scene. */
export function normalizeStaffBindScene(options = {}) {
  let raw = options.scene ?? options.t ?? ''
  if (raw === undefined || raw === null) return ''
  raw = String(raw).trim()
  if (!raw) return ''
  try {
    raw = decodeURIComponent(raw)
  } catch {
    /* keep raw */
  }
  raw = String(raw).trim()
  if (raw.startsWith(STAFF_MP_TEST_SCAN_PREFIX)) {
    raw = raw.slice(STAFF_MP_TEST_SCAN_PREFIX.length).trim()
  }
  if (!STAFF_MP_SCENE_HEX_RE.test(raw)) return ''
  return raw.toLowerCase()
}

export function parseStaffBindTestScanResult(scanResult) {
  const text = String(scanResult || '').trim()
  if (!text.startsWith(STAFF_MP_TEST_SCAN_PREFIX)) {
    return { ok: false, code: 'invalid_prefix' }
  }
  const scene = text.slice(STAFF_MP_TEST_SCAN_PREFIX.length).trim()
  if (!STAFF_MP_SCENE_HEX_RE.test(scene)) {
    return { ok: false, code: 'invalid_scene' }
  }
  return { ok: true, scene: scene.toLowerCase() }
}

export function getMiniProgramEnvVersion() {
  try {
    const info = typeof uni !== 'undefined' && uni.getAccountInfoSync
      ? uni.getAccountInfoSync()
      : null
    const v = info?.miniProgram?.envVersion
    return v || 'release'
  } catch {
    return 'release'
  }
}

/** Backend flag AND non-release env. Release always false even if server misconfigured. */
export function shouldShowStaffBindTestScan(backendTestScanEnabled) {
  if (!backendTestScanEnabled) return false
  const env = getMiniProgramEnvVersion()
  return env === 'develop' || env === 'trial'
}

export function staffBindTestPageUrl(scene) {
  const s = String(scene || '').trim().toLowerCase()
  return `/subpkg-staff/pages/staff-bind?scene=${encodeURIComponent(s)}`
}

/**
 * @returns {Promise<'cancelled'|'ok'|'error'>}
 */
export function scanStaffBindTestCode() {
  return new Promise((resolve) => {
    uni.scanCode({
      onlyFromCamera: true,
      scanType: ['qrCode'],
      success: (res) => {
        const parsed = parseStaffBindTestScanResult(res?.result)
        if (!parsed.ok) {
          uni.showToast({ title: '这不是员工绑定测试码', icon: 'none' })
          resolve('error')
          return
        }
        uni.navigateTo({
          url: staffBindTestPageUrl(parsed.scene),
          fail: () => {
            uni.showToast({ title: '暂时无法扫码，请重试', icon: 'none' })
            resolve('error')
          },
          success: () => resolve('ok'),
        })
      },
      fail: (err) => {
        const msg = String(err?.errMsg || '')
        if (msg.includes('cancel') || msg.includes('取消')) {
          resolve('cancelled')
          return
        }
        uni.showToast({ title: '暂时无法扫码，请重试', icon: 'none' })
        resolve('error')
      },
    })
  })
}
