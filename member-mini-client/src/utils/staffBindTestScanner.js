// TEMP_STAFF_SCAN_TEST
// 正式小程序上线后删除
// 只把 scene 送进现有 staff-bind；不改 wx.login / code2session / handoff。

export const STAFF_MP_TEST_SCAN_PREFIX = 'KXD_STAFF_BIND_V1:'
export const STAFF_MP_SCENE_HEX_RE = /^[0-9a-fA-F]{32}$/

/** 正式小程序码 options.scene 与测试 navigateTo ?scene= 统一。 */
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

export function staffBindTestPageUrl(scene) {
  const s = String(scene || '').trim().toLowerCase()
  // pages.json: subpkg-staff + pages/staff-bind
  return `/subpkg-staff/pages/staff-bind?scene=${encodeURIComponent(s)}`
}

/** @returns {Promise<'cancelled'|'ok'|'error'>} */
export function scanStaffBindTestCode() {
  return new Promise((resolve) => {
    uni.scanCode({
      onlyFromCamera: true,
      scanType: ['qrCode'],
      success: (res) => {
        const parsed = parseStaffBindTestScanResult(res?.result)
        if (!parsed.ok) {
          uni.showToast({ title: '这不是员工绑定码', icon: 'none' })
          resolve('error')
          return
        }
        uni.navigateTo({
          url: staffBindTestPageUrl(parsed.scene),
          fail: () => {
            uni.showToast({ title: '扫码失败，请重试', icon: 'none' })
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
        uni.showToast({ title: '扫码失败，请重试', icon: 'none' })
        resolve('error')
      },
    })
  })
}
