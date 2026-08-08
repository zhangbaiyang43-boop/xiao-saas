// TEMP_STAFF_SCAN_TEST
// 正式小程序上线后删除
import { describe, expect, it } from 'vitest'
import {
  normalizeStaffBindScene,
  parseStaffBindTestScanResult,
  staffBindTestPageUrl,
} from '../staffBindTestScanner.js'

describe('TEMP_STAFF_SCAN_TEST scanner', () => {
  it('parses valid payload and builds staff-bind url', () => {
    const scene = '0123456789abcdef0123456789abcdef'
    const r = parseStaffBindTestScanResult(`KXD_STAFF_BIND_V1:${scene}`)
    expect(r).toEqual({ ok: true, scene })
    expect(staffBindTestPageUrl(scene)).toBe(
      `/subpkg-staff/pages/staff-bind?scene=${encodeURIComponent(scene)}`
    )
  })

  it('rejects bad prefix / scene', () => {
    expect(parseStaffBindTestScanResult('https://example.com').ok).toBe(false)
    expect(parseStaffBindTestScanResult('KXD_STAFF_BIND_V1:short').ok).toBe(false)
  })

  it('normalizeStaffBindScene supports wxacode and query', () => {
    const scene = 'AaBbCcDdEeFf00112233445566778899'
    expect(normalizeStaffBindScene({ scene })).toBe(scene.toLowerCase())
    expect(normalizeStaffBindScene({ scene: `KXD_STAFF_BIND_V1:${scene}` })).toBe(scene.toLowerCase())
  })
})
