import { describe, expect, it } from 'vitest'
import { isCachedIdentityStale } from '../dining.js'

describe('dining identity cache: tenant+table collision (P0-01C)', () => {
  it('case A1 / C01: same tenant, same table -- reusable (not stale)', () => {
    expect(isCachedIdentityStale('A', 'A01', 'A', 'A01')).toBe(false)
  })

  it('case A2 / C02: same tenant, different table -- stale', () => {
    expect(isCachedIdentityStale('A', 'A01', 'A', 'A02')).toBe(true)
  })

  it('case A3 / C03: different tenant, same table string -- stale', () => {
    expect(isCachedIdentityStale('A', 'A01', 'B', 'A01')).toBe(true)
  })

  it('case A4 / C04: different tenant, different table -- stale', () => {
    expect(isCachedIdentityStale('A', 'A01', 'B', 'A02')).toBe(true)
  })

  it('case A5: no cached identity at all -- not "stale", nothing to invalidate', () => {
    expect(isCachedIdentityStale('', '', 'A', 'A01')).toBe(false)
    expect(isCachedIdentityStale('A', '', 'A', 'A01')).toBe(false)
  })
})
