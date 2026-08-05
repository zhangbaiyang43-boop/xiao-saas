import { ref, computed } from 'vue'

// 从 menu.vue 拆出来的新人券弹层状态和处理函数。逻辑跟原来在 menu.vue 里的
// 一字未改，只是搬了个位置。
//
// consumeWelcomeCoupon 是唯一一个跨功能被复用的函数——支付成功后的
// applyRewardCoupon（挑选"要展示哪张券"的逻辑，还留在 menu.vue 里）在后端没
// 返回专属奖励券时，会退回来调这个函数读本地缓存的新人券兜底，所以这里也把它
// export 出去，而不是设成组合式函数内部私有。
//
// goOrderFromWelcomeCoupon 需要把 activeTab 切到点餐 Tab——activeTab 是页面级
// 的 Tab 状态，不属于"新人券"这个功能本身，所以不在这个组合式函数内部持有，
// 而是通过 onGoOrder 回调交给调用方（menu.vue）决定具体怎么切。
export function useWelcomeCoupon(onGoOrder) {
  const showWelcomeCoupon = ref(false)
  const welcomeCouponData = ref(null)
  const welcomeCouponCondText = computed(() => {
    const min = Number(welcomeCouponData.value?.min_amount || 0)
    return min > 0 ? '满' + min.toFixed(0) + '元可用' : '无门槛可用'
  })
  const consumeWelcomeCoupon = () => {
    if (uni.getStorageSync('coupon_modal_shown') !== 'false') return null
    uni.setStorageSync('coupon_modal_shown', 'true')
    const raw = uni.getStorageSync('welcome_coupon')
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }
  const checkWelcomeCoupon = () => {
    const data = consumeWelcomeCoupon()
    if (!data) return
    welcomeCouponData.value = data
    showWelcomeCoupon.value = true
  }
  const closeWelcomeCoupon = () => {
    showWelcomeCoupon.value = false
  }
  const goOrderFromWelcomeCoupon = () => {
    showWelcomeCoupon.value = false
    if (onGoOrder) onGoOrder()
  }

  return {
    showWelcomeCoupon,
    welcomeCouponData,
    welcomeCouponCondText,
    consumeWelcomeCoupon,
    checkWelcomeCoupon,
    closeWelcomeCoupon,
    goOrderFromWelcomeCoupon,
  }
}
