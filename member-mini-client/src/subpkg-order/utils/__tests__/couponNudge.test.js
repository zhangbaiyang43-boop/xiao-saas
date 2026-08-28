import { describe, it, expect } from 'vitest'
import { buildCouponNudgeState } from '../couponNudge.mjs'

describe('buildCouponNudgeState', () => {
  it('购物车为空 / 没有券时不显示', () => {
    expect(buildCouponNudgeState({ totalPrice: 0, totalCount: 0, coupons: [{ value: 5, min_amount: 18 }] }).visible).toBe(false)
    expect(buildCouponNudgeState({ totalPrice: 30, totalCount: 2, coupons: [] }).visible).toBe(false)
  })

  it('已达门槛时 satisfied，带上折扣数字', () => {
    const s = buildCouponNudgeState({ totalPrice: 120, totalCount: 3, coupons: [{ value: 14, min_amount: 103 }] })
    expect(s.visible).toBe(true)
    expect(s.satisfied).toBe(true)
    expect(s.discountText).toBe('14')
  })

  it('触发范围跟着券面额走：差 18 元、券值 20 元 → 提示（旧的写死 15 不会提示）', () => {
    const coupons = [{ value: 20, min_amount: 100 }]
    const s = buildCouponNudgeState({ totalPrice: 82, totalCount: 2, coupons })
    expect(s.visible).toBe(true)
    expect(s.satisfied).toBe(false)
    expect(s.diffText).toBe('18')
    expect(s.discountText).toBe('20')
  })

  it('差得比券面额还多则不提示（差 30、券值 14）', () => {
    const s = buildCouponNudgeState({ totalPrice: 73, totalCount: 1, coupons: [{ value: 14, min_amount: 103 }] })
    expect(s.visible).toBe(false)
  })

  it('小额券仍按 15 元下限提示（差 12、券值 5）', () => {
    const s = buildCouponNudgeState({ totalPrice: 6, totalCount: 1, coupons: [{ value: 5, min_amount: 18 }] })
    expect(s.visible).toBe(true)
    expect(s.diffText).toBe('12')
  })
})
