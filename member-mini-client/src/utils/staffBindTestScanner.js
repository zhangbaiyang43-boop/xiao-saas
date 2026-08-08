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

export function getMiniProgramEnvVersion() {
  try {
    const info = typeof uni !== 'undefined' && uni.getAccountInfoSync
      ? uni.getAccountInfoSync()
      : null
    return info?.miniProgram?.envVersion || 'release'
  } catch {
    return 'release'
  }
}

function isNonReleaseEnv() {
  const env = getMiniProgramEnvVersion()
  return env === 'develop' || env === 'trial'
}

function looksLikeWxMiniCode(res = {}) {
  const scanType = String(res.scanType || '').toUpperCase()
  if (scanType === 'WX_CODE' || scanType.includes('WX')) return true
  if (res.path) return true
  return false
}

/** Pure branch helper for tests — does not navigate. */
export function classifyStaffBindScanRes(res = {}) {
  const parsed = parseStaffBindTestScanResult(res.result)
  if (parsed.ok) return { kind: 'test_payload', scene: parsed.scene }
  if (looksLikeWxMiniCode(res)) return { kind: 'wx_code' }
  return { kind: 'invalid' }
}

/**
 * 与桌台扫码同样的 callback 风格（见 utils/scan.js），不用 await uni.scanCode。
 * @returns {Promise<'cancelled'|'ok'|'error'>}
 */
export function scanStaffBindTestCode() {
  return new Promise((resolve) => {
    // 与项目内已工作的 scanStoreCode 一致：callback + onlyFromCamera，不限制 scanType，
    // 以便扫到正式小程序码时能拿到 path/scanType 并给出明确提示（而不是静默无反应）。
    uni.scanCode({
      onlyFromCamera: true,
      success: (res) => {
        const debug = {
          scanType: res?.scanType || '',
          hasResult: Boolean(res?.result),
          hasPath: Boolean(res?.path),
        }
        if (isNonReleaseEnv()) {
          console.log('[TEMP_STAFF_SCAN_TEST]', debug)
          uni.showToast({
            title: `扫码成功:${debug.scanType || 'unknown'}`,
            icon: 'none',
            duration: 1500,
          })
        }

        const branch = classifyStaffBindScanRes(res || {})
        const goNavigate = () => {
          if (branch.kind === 'test_payload') {
            uni.navigateTo({
              url: staffBindTestPageUrl(branch.scene),
              success: () => resolve('ok'),
              fail: (err) => {
                if (isNonReleaseEnv()) {
                  console.error('[TEMP_STAFF_SCAN_TEST] navigate fail', {
                    errMsg: err?.errMsg || '',
                  })
                  uni.showToast({ title: '员工绑定页打开失败', icon: 'none' })
                } else {
                  uni.showToast({ title: '扫码失败，请重试', icon: 'none' })
                }
                resolve('error')
              },
            })
            return
          }
          if (branch.kind === 'wx_code') {
            uni.showToast({
              title: '请扫描后台的「开发版测试二维码」，不要扫正式小程序码',
              icon: 'none',
              duration: 2500,
            })
            resolve('error')
            return
          }
          uni.showToast({ title: '这不是员工绑定测试码', icon: 'none' })
          resolve('error')
        }

        // 开发版先露出 scanType Toast，再分支处理，避免用户以为“无反应”
        if (isNonReleaseEnv()) {
          setTimeout(goNavigate, 400)
        } else {
          goNavigate()
        }
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
