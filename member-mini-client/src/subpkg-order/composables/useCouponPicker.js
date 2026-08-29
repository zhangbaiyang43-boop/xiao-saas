import { ref, computed } from 'vue'
import { parseServerTime } from '@/utils/beijingTime'

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

  const MAX_DISCOUNT_RATIO = 0.20
  // 唯一的折扣计算口径，语义必须跟后端 orders.py 建单时的 _apply_coupon 一致：
  // 门槛不达标直接判 0（跟后端"未达到优惠券使用门槛"拒单是同一件事，不是打折
  // 打得少）；FIXED 用面值，PERCENT 用"订单实际金额 × 百分比"；最终统一套用
  // 同一条 20% 封顶红线（对应后端 cap_discount_amount）。bestCouponValue/
  // discountAmount/排序全部只认这一个函数算出来的"实际能减多少钱"，不再各自
  // 拿 coupon.value 直接当金额比——那对 PERCENT 类型是错的。
  const calculateCouponDiscount = (coupon, cartTotal) => {
    if (!coupon) return 0
    const min = Number(coupon.min_amount || coupon.threshold_amount || 0)
    if (cartTotal < min) return 0
    const value = Number(coupon.value || coupon.amount || 0)
    const rawDiscount = coupon.type === 'PERCENT' ? cartTotal * value / 100 : value
    return Math.min(rawDiscount, Math.round(cartTotal * MAX_DISCOUNT_RATIO * 100) / 100)
  }

  // 顶部横幅"最高减¥X"是**招徕文案**，X 取手上券的最大面额（跟券选择器里那张券
  // 印的数字一致），不是"当前购物车实际能减多少"——购物车还空着 / 还没够门槛时，
  // 按实际能减算会得到 ¥0，横幅就变成"您有2张券，最高减¥0"，等于告诉顾客券没用。
  // 门槛差多少由券选择器展示（"还差18元可用"）。PERCENT 券没有购物车就没有确定
  // 金额，按当前购物车口径估。真正落地的折扣仍由 discountAmount 用
  // calculateCouponDiscount 算，该封顶还是封顶。
  const couponFaceValue = (coupon) => {
    if (!coupon) return 0
    if (coupon.type === 'PERCENT') return calculateCouponDiscount(coupon, getTotalPrice())
    return Number(coupon.value || coupon.amount || 0)
  }
  const bestCouponValue = computed(() => {
    if (!availableCoupons.value.length) return 0
    return Math.max(0, ...availableCoupons.value.map(couponFaceValue))
  })
  const couponBarText = computed(() => `您有${availableCoupons.value.length}张优惠券，最高减¥${formatPrice(bestCouponValue.value)}`)
  const couponBarPrefix = computed(() => `您有${availableCoupons.value.length}张优惠券，最高减`)
  const couponBarAmount = computed(() => `¥${formatPrice(bestCouponValue.value)}`)

  const discountAmount = computed(() => calculateCouponDiscount(selectedCoupon.value, getTotalPrice()))
  const finalPrice = computed(() => Math.max(getTotalPrice() - discountAmount.value, 0))
  const showCouponPicker = ref(false)

  // 实际折扣一样大的时候，谁排前面不能看后端接口凑巧返回的顺序——快过期的那张要是没被
  // 选中用掉，白白过期作废，就是纯浪费掉的营销成本。所以打平时改成比谁先过期。
  const compareCouponPriority = (a, b) => {
    const discountDiff = calculateCouponDiscount(b, getTotalPrice()) - calculateCouponDiscount(a, getTotalPrice())
    if (discountDiff !== 0) return discountDiff
    const aExpire = (parseServerTime(a.expire_time || a.valid_end_time) || new Date('2099-01-01')).getTime()
    const bExpire = (parseServerTime(b.expire_time || b.valid_end_time) || new Date('2099-01-01')).getTime()
    const expiryDiff = aExpire - bExpire
    if (expiryDiff !== 0) return expiryDiff
    return String(a.id || '').localeCompare(String(b.id || ''))
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
  const selectBestEligibleCoupon = () => {
    const best = couponPickerList.value.find(coupon => coupon.eligible) || null
    selectedCouponId.value = best ? best.id : null
    return best
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
    compareCouponPriority,
    calculateCouponDiscount,
    selectBestEligibleCoupon,
    openCouponPicker,
    closeCouponPicker,
    pickCoupon,
  }
}
