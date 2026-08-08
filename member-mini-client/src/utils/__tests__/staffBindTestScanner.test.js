// TEMP_STAFF_SCAN_TEST
// 正式小程序上线后删除
import { describe, expect, it } from 'vitest'
import {
  classifyStaffBindScanRes,
  normalizeStaffBindScene,
  parseStaffBindTestScanResult,
  staffBindTestPageUrl,
} from '../staffBindTestScanner.js'

describe('TEMP_STAFF_SCAN_TEST scanner', () => {
  it('TEST1 parses valid plain QR and builds staff-bind url', () => {
    const scene = '0123456789abcdef0123456789abcdef'
    const r = parseStaffBindTestScanResult(`KXD_STAFF_BIND_V1:${scene}`)
    expect(r).toEqual({ ok: true, scene })
    expect(staffBindTestPageUrl(scene)).toBe(
      `/subpkg-staff/pages/staff-bind?scene=${encodeURIComponent(scene)}`
    )
    expect(classifyStaffBindScanRes({ result: `KXD_STAFF_BIND_V1:${scene}`, scanType: 'QR_CODE' })).toEqual({
      kind: 'test_payload',
      scene,
    })
  })

  it('TEST3 WX_CODE / path → wx_code branch (do not parse path)', () => {
    expect(classifyStaffBindScanRes({ scanType: 'WX_CODE', path: 'subpkg-staff/pages/staff-bind?scene=abc', result: '' })).toEqual({
      kind: 'wx_code',
    })
    expect(classifyStaffBindScanRes({ path: '/pages/index/index', result: '' }).kind).toBe('wx_code')
  })

  it('TEST4 rejects random url', () => {
    expect(classifyStaffBindScanRes({ result: 'https://example.com', scanType: 'QR_CODE' }).kind).toBe('invalid')
    expect(parseStaffBindTestScanResult('KXD_STAFF_BIND_V1:short').ok).toBe(false)
  })

  it('normalizeStaffBindScene supports navigateTo query scene', () => {
    const scene = 'AaBbCcDdEeFf00112233445566778899'
    expect(normalizeStaffBindScene({ scene })).toBe(scene.toLowerCase())
    expect(normalizeStaffBindScene({ scene: `KXD_STAFF_BIND_V1:${scene}` })).toBe(scene.toLowerCase())
  })
})
