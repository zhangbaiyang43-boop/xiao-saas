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
  // 用 PNG 而不是 WebP：WebP 版本在真机微信运行时被证实 404（Runtime 排查见
  // git 历史），PNG 是 WebP 性能优化之前最后一版已验证能正常显示的版本，
  // 且带 alpha 透明通道（当前 WebP 已丢失透明通道，改成纯黑底）。V1 稳定性优先。
  const MEMBER_LEVEL_BADGES = { LV1: '/static/member-levels/level-lv1.png', LV2: '/static/member-levels/level-lv2.png', LV3: '/static/member-levels/level-lv3.png' }
  const memberLevelBadgeSrc = computed(() => MEMBER_LEVEL_BADGES[bannerInfo.value?.levelCode] || MEMBER_LEVEL_BADGES.LV1)
  // 跟 growth.vue 的 LEVEL_CARD_META 保持同一份数值（背景图路径 + 色调 tint），
  // 那边是已验证的权威来源，这里照抄，不重新设计。textPrimary/Secondary/Tertiary
  // 是本轮新增的文字前景色——真机验证过原来那一套不分等级、统一用的浅金色
  // （#f3e6cf 系）在 LV1 的亮绿底上对比度不够，字发虚。三级文字都按各等级底色
  // 单独选深色，不再跨等级共用一套。
  const MEMBER_LEVEL_CARD_META = {
    LV1: { bg: '/static/member-levels/card-bg-lv1.jpg', tint: '6,163,94', textPrimary: '#123B2A', textSecondary: '#35634F', textTertiary: '#527563' },
    LV2: { bg: '/static/member-levels/card-bg-lv2.jpg', tint: '100,112,128', textPrimary: '#26323A', textSecondary: '#53616B', textTertiary: '#6F7B83' },
    LV3: { bg: '/static/member-levels/card-bg-lv3.jpg', tint: '176,130,32', textPrimary: '#4A3210', textSecondary: '#715224', textTertiary: '#8A6A37' },
  }
  // 真机微信运行时证实：动态 inline style 里引用本地静态 jpg 当背景图不可靠，
  // 本地图不会显示（同一张图片改用 <image :src> 在同一环境能正常加载）。所以
  // 背景改成真正的 <image> 节点，这里只出 src；tint 渐变单独出一份纯色叠加层
  // style，跟背景图分开，两者在 MemberCard.vue 里分层叠加。
  const memberIdentityCardBgSrc = computed(() => {
    const meta = MEMBER_LEVEL_CARD_META[bannerInfo.value?.levelCode] || MEMBER_LEVEL_CARD_META.LV1
    return meta.bg
  })
  const memberIdentityCardTintStyle = computed(() => {
    const meta = MEMBER_LEVEL_CARD_META[bannerInfo.value?.levelCode] || MEMBER_LEVEL_CARD_META.LV1
    return `background: linear-gradient(135deg, rgba(${meta.tint},0.68), rgba(${meta.tint},0.42));`
  })
  // 单一入口下发三级文字色 CSS 变量，MemberCard.vue 里所有会员身份区域的文字都
  // 通过 var(--member-text-*) 读这三个变量，不在多处各写一份等级色映射。
  const memberIdentityCardForegroundStyle = computed(() => {
    const meta = MEMBER_LEVEL_CARD_META[bannerInfo.value?.levelCode] || MEMBER_LEVEL_CARD_META.LV1
    return `--member-text-primary:${meta.textPrimary};--member-text-secondary:${meta.textSecondary};--member-text-tertiary:${meta.textTertiary};`
  })
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
    memberIdentityCardBgSrc,
    memberIdentityCardTintStyle,
    memberIdentityCardForegroundStyle,
    memberProgressPercent,
    memberUpgradeText,
    usableMemberCoupons,
    goOrderFromMember,
    useMemberCoupon,
  }
}
