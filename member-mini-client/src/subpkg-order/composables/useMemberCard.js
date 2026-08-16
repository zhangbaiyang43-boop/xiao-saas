import { ref, computed } from 'vue'

// 从 menu.vue 拆出来的会员卡片状态和纯派生计算——会员等级、成长值进度、会员
// 专属券列表这些只读展示逻辑。逻辑跟原来在 menu.vue 里的一字未改，只是搬了个
// 位置。
//
// 特意没有拆进来的东西，留在 menu.vue 里：
// - loadMemberStatus / handleMemberCardAuth：这两个是"登录 + 拉会员资料"的
//   完整流程函数，会同时改 isCustomerLoggedIn、availableCoupons（购物车结算
//   用的优惠券列表）、authStateVersion 等好几个跟"会员卡片"本身无关的页面级
//   状态，硬拆进来只会让这个组合式函数背上一堆不属于它的依赖。
// - availableCoupons/isCustomerLoggedIn/authStateVersion：这几个是全页面共用
//   的状态（购物车结算、优惠券横幅、桌台账单都要读），不是会员卡专属的。
//
// shopCreatedAt 是外部（menu.vue）拥有的 ref，这里只读需要的那一个字段，不接
// 管它的生命周期；onGoOrder/onUseCoupon 都是回调而不是直接传 ref 进来——一是
// activeTab、selectedCouponId 都不属于"会员卡"这个功能，二是 selectedCouponId
// 在 menu.vue 里声明的位置比这个组合式函数调用的位置靠后，传回调避免了"用到
// 一个还没声明的 const"这种时序问题（回调体要等真正点击时才会执行，那时候
// selectedCouponId 早就声明好了）。
export function useMemberCard({ shopCreatedAt, formatPrice, onGoOrder, onUseCoupon }) {
  const bannerInfo = ref(null)
  const isMember = ref(false)
  const memberLoading = ref(false)
  const memberAuthorizing = ref(false)

  const memberSinceText = computed(() => {
    const year = new Date(shopCreatedAt.value).getFullYear()
    return Number.isNaN(year) ? '' : '会员自 ' + year + ' 年'
  })

  const memberLevelLabel = computed(() => bannerInfo.value?.levelLabel || '普通会员')
  const MEMBER_LEVEL_BADGES = { LV1: '/static/member-levels/level-lv1.webp', LV2: '/static/member-levels/level-lv2.webp', LV3: '/static/member-levels/level-lv3.webp' }
  const memberLevelBadgeSrc = computed(() => MEMBER_LEVEL_BADGES[bannerInfo.value?.levelCode] || MEMBER_LEVEL_BADGES.LV1)
  const memberProgressPercent = computed(() => {
    const current = Number(bannerInfo.value?.growth || bannerInfo.value?.growthValue || 0)
    const target = Number(bannerInfo.value?.nextGrowth || 0)
    if (!target || target <= 0) return 0
    return Math.max(0, Math.min(100, Math.round((current / target) * 100)))
  })
  const memberUpgradeText = computed(() => {
    const amount = Number(bannerInfo.value?.nextUpgradeAmount || 0)
    return amount > 0 ? '再消费 ¥' + formatPrice(amount) + ' 升级' : ''
  })
  const usableMemberCoupons = computed(() => (bannerInfo.value?.coupons || []).slice(0, 3))

  const goOrderFromMember = () => { if (onGoOrder) onGoOrder() }
  const useMemberCoupon = (coupon) => {
    if (onUseCoupon) onUseCoupon(coupon?.id || coupon?.coupon_id || null)
    if (onGoOrder) onGoOrder()
  }

  return {
    bannerInfo,
    isMember,
    memberLoading,
    memberAuthorizing,
    memberSinceText,
    memberLevelLabel,
    memberLevelBadgeSrc,
    memberProgressPercent,
    memberUpgradeText,
    usableMemberCoupons,
    goOrderFromMember,
    useMemberCoupon,
  }
}
