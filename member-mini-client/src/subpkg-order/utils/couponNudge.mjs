const DEFAULT_NUDGE_RANGE = 15

const numericValue = (value) => {
  const n = Number(value || 0)
  return Number.isFinite(n) ? n : 0
}

const formatMoney = (value) => {
  const n = numericValue(value)
  return n % 1 === 0 ? String(n) : n.toFixed(2)
}

const couponThreshold = (coupon) => numericValue(coupon?.min_amount ?? coupon?.threshold_amount ?? coupon?.threshold)
const couponDiscount = (coupon) => numericValue(coupon?.value ?? coupon?.amount ?? coupon?.discount_amount)

const toState = ({ coupon, diff = 0, satisfied }) => ({
  visible: true,
  satisfied,
  coupon,
  diff,
  diffText: formatMoney(diff),
  thresholdText: formatMoney(couponThreshold(coupon)),
  discountText: formatMoney(couponDiscount(coupon)),
})

export const buildCouponNudgeState = ({ totalPrice = 0, totalCount = 0, coupons = [], nudgeRange = DEFAULT_NUDGE_RANGE } = {}) => {
  const total = numericValue(totalPrice)
  if (numericValue(totalCount) <= 0 || !Array.isArray(coupons) || coupons.length <= 0) {
    return { visible: false }
  }

  const usefulCoupons = coupons.filter(coupon => couponThreshold(coupon) > 0 && couponDiscount(coupon) > 0)
  if (!usefulCoupons.length) return { visible: false }

  const eligible = usefulCoupons
    .filter(coupon => total >= couponThreshold(coupon))
    .sort((a, b) => couponDiscount(b) - couponDiscount(a) || couponThreshold(b) - couponThreshold(a))

  if (eligible.length) {
    return toState({ coupon: eligible[0], satisfied: true })
  }

  const closest = usefulCoupons
    .map(coupon => ({ coupon, diff: couponThreshold(coupon) - total }))
    .filter(item => item.diff > 0 && item.diff <= nudgeRange)
    .sort((a, b) => a.diff - b.diff || couponDiscount(b.coupon) - couponDiscount(a.coupon))[0]

  return closest ? toState({ coupon: closest.coupon, diff: closest.diff, satisfied: false }) : { visible: false }
}
