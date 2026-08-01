import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildCouponNudgeState } from '../src/subpkg-order/utils/couponNudge.mjs'

test('shows nearest coupon gap when cart is below threshold', () => {
  const state = buildCouponNudgeState({
    totalPrice: 32.8,
    totalCount: 1,
    coupons: [
      { id: 'high', min_amount: 60, value: 8 },
      { id: 'near', min_amount: 33, value: 2 },
    ],
  })

  assert.equal(state.visible, true)
  assert.equal(state.satisfied, false)
  assert.equal(state.diffText, '0.20')
  assert.equal(state.thresholdText, '33')
  assert.equal(state.discountText, '2')
})

test('shows satisfied state for the best eligible coupon', () => {
  const state = buildCouponNudgeState({
    totalPrice: 54,
    totalCount: 2,
    coupons: [
      { id: 'small', min_amount: 33, value: 2 },
      { id: 'best', min_amount: 50, value: 6 },
    ],
  })

  assert.equal(state.visible, true)
  assert.equal(state.satisfied, true)
  assert.equal(state.thresholdText, '50')
  assert.equal(state.discountText, '6')
})

test('hides when there are no useful coupons or no cart items', () => {
  assert.equal(buildCouponNudgeState({ totalPrice: 0, totalCount: 0, coupons: [{ min_amount: 33, value: 2 }] }).visible, false)
  assert.equal(buildCouponNudgeState({ totalPrice: 20, totalCount: 1, coupons: [] }).visible, false)
})
