import { describe, expect, it } from 'vitest'
import { shouldShowInitialHint, shouldShowStatusCallout } from '../order-bubble-logic.js'

describe('order bubble: initial hint vs status-change callout', () => {
  it('case A: first order lands as paid — hint shows, callout does not', () => {
    expect(shouldShowInitialHint(true, false)).toBe(true)
    expect(shouldShowStatusCallout(true, false, 'paid', 'empty')).toBe(false)
  })

  it('case B: first order lands as preparing — hint shows, callout does not', () => {
    expect(shouldShowInitialHint(true, false)).toBe(true)
    expect(shouldShowStatusCallout(true, false, 'preparing', 'empty')).toBe(false)
  })

  it('case B (mine.vue placeholder convention): first order lands as preparing while placeholder was "paid" — callout still suppressed', () => {
    expect(shouldShowStatusCallout(true, false, 'preparing', 'paid')).toBe(false)
  })

  it('case C: bubble already visible, paid -> preparing — callout fires', () => {
    expect(shouldShowInitialHint(true, true)).toBe(false)
    expect(shouldShowStatusCallout(true, true, 'preparing', 'paid')).toBe(true)
  })

  it('case D: bubble already visible, preparing -> served — callout fires', () => {
    expect(shouldShowStatusCallout(true, true, 'served', 'preparing')).toBe(true)
  })

  it('case E: tone unchanged — callout does not fire', () => {
    expect(shouldShowStatusCallout(true, true, 'preparing', 'preparing')).toBe(false)
  })

  it('case F: bubble stays hidden throughout — neither hint nor callout fire', () => {
    expect(shouldShowInitialHint(false, false)).toBe(false)
    expect(shouldShowStatusCallout(false, false, 'empty', 'empty')).toBe(false)
  })

  it('bubble becoming hidden again never triggers a callout, regardless of tone', () => {
    expect(shouldShowStatusCallout(false, true, 'settled', 'served')).toBe(false)
  })
})
