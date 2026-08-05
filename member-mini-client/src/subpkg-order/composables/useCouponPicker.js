import { ref, computed } from 'vue'

// 从 menu.vue 拆出来的优惠券横幅 + 优惠券选择器状态。逻辑跟原来在 menu.vue 里
// 的一字未改，只是搬了个位置。
//
// availableCoupons 特意没有拆进来——它是全页面共用的"优惠券库存"，会员资料
// 拉取（loadMemberStatus）和单独的券刷新（refreshAvailableCoupons）两个地方
// 都会写它，不是"优惠券选择器"独有的状态，所以作为外部 ref 传进来，这个组合
// 式函数只读不接管它的生命周期。isCustomerLoggedIn/formatPrice 同理。
//
// totalPrice 传的是取值函数 getTotalPrice 而不是 ref 本身——因为 totalPrice
// 在 menu.vue 里声明的位置比这个组合式函数调用的位置靠后，直接把 ref 当参数传
// 会在它还没声明时就去读，报"暂时性死区"的错。传函数不会有这个问题，函数体
// 要等 computed 真正求值的时候才会执行，那时候 totalPrice 早就声明好了；对
// 响应式追踪也没有影响，Vue 认的是"计算过程中实际读了哪个 ref"，不是"这个 ref
// 是通过什么方式传进来的"。
export function useCouponPicker({ availableCoupons, getTotalPrice, isCustomerLoggedIn, formatPrice }) {
  const selectedCouponId = ref(null)
  const selectedCoupon = computed(() =>
    availableCoupons.value.find(c => c.id === selectedCouponId.value) || null
  )
  const couponBarVisible = computed(() => isCustomerLoggedIn.value && availableCoupons.value.length > 0)
  const bestCouponValue = computed(() => {
    if (!availableCoupons.value.length) return 0
    return Math.max(...availableCoupons.value.map(c => Number(c.value || c.amount || 0)))
  })
  const couponBarText = computed(() => `您有${availableCoupons.value.length}张优惠券，最高减¥${formatPrice(bestCouponValue.value)}`)
  const couponBarPrefix = computed(() => `您有${availableCoupons.value.length}张优惠券，最高减`)
  const couponBarAmount = computed(() => `¥${formatPrice(bestCouponValue.value)}`)

  const MAX_DISCOUNT_RATIO = 0.20
  const discountAmount = computed(() => {
    if (!selectedCoupon.value) return 0
    const min = Number(selectedCoupon.value.min_amount || selectedCoupon.value.threshold_amount || 0)
    if (getTotalPrice() < min) return 0
    const rawDiscount = Number(selectedCoupon.value.value || selectedCoupon.value.amount || 0)
    return Math.min(rawDiscount, Math.round(getTotalPrice() * MAX_DISCOUNT_RATIO * 100) / 100)
  })
  const finalPrice = computed(() => Math.max(getTotalPrice() - discountAmount.value, 0))
  const showCouponPicker = ref(false)

  // 面额一样大的时候，谁排前面不能看后端接口凑巧返回的顺序——快过期的那张要是没被
  // 选中用掉，白白过期作废，就是纯浪费掉的营销成本。所以打平时改成比谁先过期。
  const compareCouponPriority = (a, b) => {
    const valueDiff = Number(b.value || b.amount || 0) - Number(a.value || a.amount || 0)
    if (valueDiff !== 0) return valueDiff
    const aExpire = new Date(a.expire_time || a.valid_end_time || '2099-01-01').getTime()
    const bExpire = new Date(b.expire_time || b.valid_end_time || '2099-01-01').getTime()
    return aExpire - bExpire
  }
  const couponPickerList = computed(() =>
    [...availableCoupons.value]
      .map(c => ({ ...c, eligible: getTotalPrice() >= Number(c.min_amount || c.threshold_amount || 0) }))
      .sort((a, b) => (b.eligible - a.eligible) || compareCouponPriority(a, b))
  )
  const openCouponPicker = () => { showCouponPicker.value = true }
  const closeCouponPicker = () => { showCouponPicker.value = false }
  const pickCoupon = (coupon) => {
    if (coupon && !coupon.eligible) return
    selectedCouponId.value = coupon ? coupon.id : null
    showCouponPicker.value = false
  }

  return {
    selectedCouponId,
    selectedCoupon,
    couponBarVisible,
    bestCouponValue,
    couponBarText,
    couponBarPrefix,
    couponBarAmount,
    discountAmount,
    finalPrice,
    showCouponPicker,
    couponPickerList,
    openCouponPicker,
    closeCouponPicker,
    pickCoupon,
  }
}
