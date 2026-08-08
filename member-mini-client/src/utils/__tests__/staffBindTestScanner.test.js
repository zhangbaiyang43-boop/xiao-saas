// TEMP_STAFF_BIND_TEST_SCAN
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getMiniProgramEnvVersion,
  normalizeStaffBindScene,
  parseStaffBindTestScanResult,
  shouldShowStaffBindTestScan,
  staffBindTestPageUrl,
} from '../staffBindTestScanner.js'

describe('staffBindTestScanner TEMP', () => {
  beforeEach(() => {
    vi.stubGlobal('uni', {
      getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
    })
  })

  it('TEST-01/02 develop+trial show when flag true', () => {
    uni.getAccountInfoSync = () => ({ miniProgram: { envVersion: 'develop' } })
    expect(shouldShowStaffBindTestScan(true)).toBe(true)
    uni.getAccountInfoSync = () => ({ miniProgram: { envVersion: 'trial' } })
    expect(shouldShowStaffBindTestScan(true)).toBe(true)
  })

  it('TEST-03 release never shows even if flag true', () => {
    uni.getAccountInfoSync = () => ({ miniProgram: { envVersion: 'release' } })
    expect(shouldShowStaffBindTestScan(true)).toBe(false)
  })

  it('TEST-04 flag false hides on develop', () => {
    uni.getAccountInfoSync = () => ({ miniProgram: { envVersion: 'develop' } })
    expect(shouldShowStaffBindTestScan(false)).toBe(false)
  })

  it('TEST-05 valid payload parses to scene', () => {
    const scene = '0123456789abcdef0123456789abcdef'
    const r = parseStaffBindTestScanResult(`KXD_STAFF_BIND_V1:${scene}`)
    expect(r).toEqual({ ok: true, scene })
    expect(staffBindTestPageUrl(scene)).toContain(`scene=${encodeURIComponent(scene)}`)
  })

  it('TEST-06 invalid prefix rejected', () => {
    expect(parseStaffBindTestScanResult('https://example.com').ok).toBe(false)
    expect(parseStaffBindTestScanResult('KXD_STAFF_BIND_V2:0123456789abcdef0123456789abcdef').ok).toBe(false)
  })

  it('TEST-07 invalid scene format rejected', () => {
    expect(parseStaffBindTestScanResult('KXD_STAFF_BIND_V1:short').ok).toBe(false)
    expect(parseStaffBindTestScanResult('KXD_STAFF_BIND_V1:zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz').ok).toBe(false)
  })

  it('normalizeStaffBindScene unifies wxacode and query', () => {
    const scene = 'AaBbCcDdEeFf00112233445566778899'
    expect(normalizeStaffBindScene({ scene })).toBe(scene.toLowerCase())
    expect(normalizeStaffBindScene({ scene: encodeURIComponent(scene) })).toBe(scene.toLowerCase())
    expect(normalizeStaffBindScene({ scene: `KXD_STAFF_BIND_V1:${scene}` })).toBe(scene.toLowerCase())
    expect(normalizeStaffBindScene({ scene: 'not-hex' })).toBe('')
  })

  it('getMiniProgramEnvVersion defaults release on missing API', () => {
    uni.getAccountInfoSync = () => {
      throw new Error('no')
    }
    expect(getMiniProgramEnvVersion()).toBe('release')
  })
})
