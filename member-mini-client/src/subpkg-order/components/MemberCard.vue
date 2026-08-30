<template>
  <scroll-view class="tab-scroll" scroll-y>
    <view v-if="bannerInfo" class="card-tab member-center">
      <view class="member-identity-card tap-shrink" @click="uni.navigateTo({ url: '/subpkg-member/pages/growth' })">
        <image
          v-if="memberIdentityCardBgSrc"
          class="member-identity-card-bg"
          :src="memberIdentityCardBgSrc"
          mode="aspectFill"
        />
        <view class="member-identity-card-tint" :style="memberIdentityCardTintStyle"></view>
        <view class="member-identity-card-content" :style="memberIdentityCardForegroundStyle">
          <view class="mic-glow"></view>
          <view class="mic-issuer"><text>{{ shopName }} · 甄选会员</text></view>
          <view class="mic-body">
            <view class="member-avatar">
              <image v-if="bannerInfo.avatar" class="member-avatar-img" :src="bannerInfo.avatar" mode="aspectFill" />
              <image v-else class="member-avatar-badge" :src="memberLevelBadgeSrc" mode="aspectFit" />
            </view>
            <view class="member-identity-main">
              <view class="mic-crest-row">
                <text class="member-level">{{ memberLevelLabel }}</text>
              </view>
              <text class="mic-sub">MEMBER</text>
            </view>
            <text class="mic-chevron iconfont icon-roundright"></text>
          </view>
          <view v-if="memberUpgradeText" class="member-progress-wrap">
            <view class="member-progress-track"><view class="member-progress-fill" :style="{ width: memberProgressPercent + '%' }"></view></view>
            <text class="member-upgrade-text">{{ memberUpgradeText }}</text>
          </view>
          <view v-if="bannerInfo.memberNo || memberSinceText" class="mic-footer">
            <text v-if="bannerInfo.memberNo" class="mic-number">{{ 'NO. ' + bannerInfo.memberNo }}</text>
            <text v-if="memberSinceText" class="mic-since">{{ memberSinceText }}</text>
          </view>
        </view>
      </view>

      <view class="member-assets-card">
        <view class="member-asset-item" @click="uni.navigateTo({ url: '/subpkg-member/pages/points' })">
          <text class="member-asset-value">{{ bannerInfo.points || 0 }}</text>
          <text class="member-asset-label">积分</text>
        </view>
        <view class="member-asset-divider"></view>
        <view class="member-asset-item" @click="uni.navigateTo({ url: '/subpkg-coupon/pages/list' })">
          <text class="member-asset-value">{{ bannerInfo.couponCount }}</text>
          <text class="member-asset-label">优惠券</text>
        </view>
      </view>

      <view class="member-main-action-card">
        <text class="member-action-title">{{ memberActionTitle }}</text>
        <view class="member-action-btn" @click="$emit('go-order')"><text>去点餐</text></view>
      </view>

      <view v-if="usableMemberCoupons.length" class="member-section">
        <text class="member-section-title">可用优惠券</text>
        <text class="member-coupon-hint">单张券每次最多抵订单金额的 20%，实际优惠以结算页为准</text>
        <view class="member-coupon-list">
          <view v-for="coupon in usableMemberCoupons" :key="coupon.id || coupon.coupon_id || coupon.name" class="member-coupon-card" @click="$emit('use-coupon', coupon)">
            <view class="member-coupon-value">
              <text class="member-coupon-yen">¥</text>
              <text class="member-coupon-amount">{{ couponAmountText(coupon) }}</text>
            </view>
            <view class="member-coupon-info">
              <text class="member-coupon-condition">{{ couponConditionText(coupon) }}</text>
              <text class="member-coupon-time">{{ couponValidityText(coupon) }}</text>
            </view>
            <view class="member-coupon-use"><text>立即使用</text></view>
          </view>
        </view>
      </view>

      <view class="member-service-card">
        <view class="member-service-row" @click="uni.navigateTo({ url: '/subpkg-member/pages/points' })">
          <view class="member-service-icon"><text class="iconfont icon-timefill"></text></view>
          <text class="member-service-label">积分明细</text>
          <text class="member-service-arrow iconfont icon-roundright"></text>
        </view>
        <view class="member-service-row" @click="uni.navigateTo({ url: '/subpkg-coupon/pages/list' })">
          <view class="member-service-icon"><text class="iconfont icon-youhuiquan"></text></view>
          <text class="member-service-label">优惠券</text>
          <text class="member-service-arrow iconfont icon-roundright"></text>
        </view>
      </view>
    </view>
    <view v-else-if="hasCustomerIdentity" class="card-tab-empty">
      <text class="cte-title">会员中心</text>
      <text class="cte-desc">普通会员</text>
      <view class="cte-btn cte-btn-plain" @click="$emit('reload')">
        <text>{{ memberLoading ? '加载中...' : '重新加载' }}</text>
      </view>
      <text class="cte-secondary" @click="$emit('go-order')">去点餐</text>
    </view>
    <view v-else class="card-tab-empty">
      <text class="cte-title">会员中心</text>
      <text class="cte-desc">{{ newCustomerHookText }}</text>
      <button
        class="cte-btn"
        open-type="getPhoneNumber"
        :disabled="memberAuthorizing"
        @getphonenumber="$emit('phone-auth', $event)"
      >
        <text>{{ memberAuthorizing ? '授权中...' : '查看会员权益' }}</text>
      </button>
      <text class="cte-secondary" @click="$emit('go-order')">去点餐</text>
    </view>
  </scroll-view>
</template>

<script>
// 从 menu.vue 拆出来的会员卡片区块（原来是 activeTab==='card' 那一段模板）。
// 纯展示组件，不带任何业务逻辑——所有需要改父组件状态的动作（切 Tab、重新加载、
// 用券、手机号授权）都只 emit 出去，真正的处理函数还是原来 menu.vue 里那几个
// （goOrderFromMember/loadMemberStatus/useMemberCoupon/handleMemberCardAuth），
// 一行都没有改，只是从内联模板换成了从父组件监听事件调用。这样拆分不改变任何
// 业务行为，只是把模板挪了地方。
export default {
  name: 'MemberCard',
  props: {
    bannerInfo: { type: Object, default: null },
    shopName: { type: String, default: '' },
    memberLevelBadgeSrc: { type: String, default: '' },
    memberIdentityCardBgSrc: { type: String, default: '' },
    memberIdentityCardTintStyle: { type: String, default: '' },
    memberIdentityCardForegroundStyle: { type: String, default: '' },
    memberLevelLabel: { type: String, default: '' },
    memberUpgradeText: { type: String, default: '' },
    memberProgressPercent: { type: Number, default: 0 },
    memberSinceText: { type: String, default: '' },
    usableMemberCoupons: { type: Array, default: () => [] },
    hasCustomerIdentity: { type: Boolean, default: false },
    memberLoading: { type: Boolean, default: false },
    newCustomerHookText: { type: String, default: '' },
    memberAuthorizing: { type: Boolean, default: false },
    // 三个纯格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑），
    // 保证跟父组件其它地方用到的格式化结果 100% 一致，不会出现"拆分之后数字
    // 显示得不一样"这种偏差。
    couponAmountText: { type: Function, required: true },
    couponConditionText: { type: Function, required: true },
    couponValidityText: { type: Function, required: true },
  },
  emits: ['go-order', 'reload', 'use-coupon', 'phone-auth'],
  computed: {
    memberActionTitle() {
      const count = Number(this.bannerInfo && this.bannerInfo.couponCount || 0)
      if (count > 0) return '您有' + count + '张优惠券可用'
      return '去点餐，结算自动用优惠'
    },
  },
}
</script>

<style lang="scss">
.card-tab.member-center {
  padding: 28rpx 32rpx calc(132rpx + env(safe-area-inset-bottom));
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  box-sizing: border-box;
}


.member-identity-card { position: relative; padding: 30rpx 32rpx 26rpx; border-radius: 32rpx; background: linear-gradient(120deg,#15392a 0%,#0a2216 42%,#1c4530 100%); box-sizing: border-box; overflow: hidden; animation: micBorderGlow 3.2s ease-in-out infinite; }


.member-identity-card::before { content:''; position: absolute; inset: 0; opacity: .5; background-image: repeating-linear-gradient(135deg, rgba(255,255,255,.035) 0px, rgba(255,255,255,.035) 1px, transparent 1px, transparent 7px); pointer-events: none; }


// 会员等级背景改成真正的 <image>，而不是 inline style 里的 background-image: url(...)：
// 真机微信运行时证实本地 /static jpg 用 CSS background-image 加载不出来，同一张图
// 用 <image :src> 在同一环境能正常显示。背景图（z0）+ 色调叠加层（z1）+ 原有内容
// （z2，包在 member-identity-card-content 里）三层叠加；.member-identity-card 自己
// 的 background（上面那行）留着不动，图片加载失败时兜底，不会让卡片空白。
.member-identity-card-bg { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 0; }


.member-identity-card-tint { position: absolute; inset: 0; z-index: 1; }


.member-identity-card-content {
  position: relative;
  z-index: 2;
  // LV1 兜底值：memberIdentityCardForegroundStyle 意外为空时，行内 style 不会
  // 覆盖这三个变量，靠这里的默认值保证至少 LV1 底色下文字仍然可读。
  --member-text-primary: #123B2A;
  --member-text-secondary: #35634F;
  --member-text-tertiary: #527563;
}


.mic-glow { position: absolute; right: -68rpx; top: -68rpx; width: 260rpx; height: 260rpx; border-radius: 50%; background: radial-gradient(circle, rgba(212,175,110,.2), transparent 70%); pointer-events: none; }


.mic-issuer { position: relative; z-index: 1; font-size: 21rpx; font-weight: 800; letter-spacing: 2rpx; color: var(--member-text-secondary); text-transform: uppercase; }


.mic-body { position: relative; z-index: 1; margin-top: 20rpx; display: flex; align-items: center; gap: 22rpx; }


.member-avatar { width: 100rpx; height: 100rpx; border-radius: 50%; background: #16311f; display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }


.member-avatar text { color: #f3e6cf; font-size: 34rpx; line-height: 48rpx; font-weight: 900; }


.member-avatar-img { width: 100%; height: 100%; }


.member-avatar-badge { width: 96rpx; height: 96rpx; display: block; flex-shrink: 0; animation: micBadgePulse 3.2s ease-in-out infinite; }


.member-identity-main { flex: 1; min-width: 0; }


.mic-crest-row { display: flex; align-items: center; gap: 10rpx; min-width: 0; }


.member-level { display: block; font-size: 38rpx; line-height: 50rpx; font-weight: 900; color: var(--member-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.mic-sub { display: block; margin-top: 6rpx; font-size: 21rpx; color: var(--member-text-secondary); font-weight: 700; letter-spacing: 3rpx; text-transform: uppercase; }


.mic-chevron { position: relative; z-index: 1; color: var(--member-text-tertiary); font-size: 28rpx; flex-shrink: 0; }


.member-progress-wrap { position: relative; z-index: 1; margin-top: 22rpx; }


.member-progress-track { height: 8rpx; border-radius: 999rpx; background: rgba(232,202,160,.16); overflow: hidden; }


.member-progress-fill { height: 100%; border-radius: 999rpx; background: linear-gradient(90deg,#c9a668,#f3e6cf); }


.member-upgrade-text { display: block; margin-top: 10rpx; color: var(--member-text-secondary); font-size: 22rpx; line-height: 32rpx; font-weight: 700; }


.mic-footer { position: relative; z-index: 1; margin-top: 22rpx; padding-top: 18rpx; border-top: 1rpx solid rgba(232,202,160,.16); display: flex; align-items: center; justify-content: space-between; }


.mic-number { font-size: 22rpx; font-weight: 700; letter-spacing: 3rpx; color: var(--member-text-tertiary); }


.mic-since { font-size: 20rpx; color: var(--member-text-tertiary); font-weight: 700; }


.member-assets-card { min-height: 168rpx; background: #fff; border-radius: 32rpx; display: flex; align-items: stretch; padding: 28rpx 0; box-sizing: border-box; }


.member-asset-item { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8rpx; }


.member-asset-item:active { opacity: .72; }


.member-asset-divider { width: 1rpx; margin: 12rpx 0; background: var(--border); }


.member-asset-value { color: var(--text-1); font-size: 38rpx; line-height: 46rpx; font-weight: 900; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.member-asset-label { color: var(--text-1); font-size: 26rpx; line-height: 36rpx; font-weight: 700; }


.member-main-action-card { padding: 34rpx; border-radius: var(--radius-hero); background: var(--brand-gradient); box-sizing: border-box; }


.member-action-title { display: block; color: #fff; font-size: 36rpx; line-height: 48rpx; font-weight: 900; }


.member-action-btn { margin-top: 24rpx; height: 96rpx; border-radius: 48rpx; background: #fff; display: flex; align-items: center; justify-content: center; }


.member-action-btn:active { transform: scale(.98); }


.member-action-btn text { color: var(--brand); font-size: 32rpx; line-height: 44rpx; font-weight: 900; }


.member-section { display: flex; flex-direction: column; gap: 16rpx; }


.member-section-title { color: var(--text-1); font-size: 32rpx; line-height: 44rpx; font-weight: 900; }
.member-coupon-hint { margin-top: -4rpx; color: var(--text-3); font-size: 22rpx; line-height: 1.4; }


.member-coupon-list { display: flex; flex-direction: column; gap: 16rpx; }


.member-coupon-card { min-height: 132rpx; padding: 24rpx; border-radius: 28rpx; background: #fff; display: flex; align-items: center; gap: 20rpx; box-sizing: border-box; }


.member-coupon-card:active { opacity: .74; }


.member-coupon-value { width: 118rpx; flex-shrink: 0; color: var(--brand); display: flex; align-items: baseline; justify-content: center; }


.member-coupon-yen { font-size: 26rpx; line-height: 34rpx; font-weight: 900; }


.member-coupon-amount { font-size: 48rpx; line-height: 56rpx; font-weight: 900; }


.member-coupon-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8rpx; }


.member-coupon-condition { color: var(--text-1); font-size: 28rpx; line-height: 38rpx; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.member-coupon-time { color: var(--text-3); font-size: 24rpx; line-height: 34rpx; }


.member-coupon-use { height: 64rpx; padding: 0 24rpx; border-radius: 32rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }


.member-coupon-use text { color: #fff; font-size: 24rpx; line-height: 34rpx; font-weight: 800; }


.member-service-card { background: #fff; border-radius: 32rpx; overflow: hidden; }


.member-service-row { min-height: 96rpx; padding: 0 30rpx; display: flex; align-items: center; gap: 20rpx; color: var(--text-1); font-size: 30rpx; line-height: 42rpx; font-weight: 800; box-sizing: border-box; }


.member-service-row + .member-service-row { border-top: 1rpx solid var(--border); }


.member-service-row:active { background: #F7F9FA; }


.member-service-icon { width: 56rpx; height: 56rpx; border-radius: 16rpx; background: #E8F8EF; color: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.member-service-icon .iconfont { font-size: 28rpx; }


.member-service-label { flex: 1; min-width: 0; }


.member-service-arrow { color: #B0B7C0; font-size: 26rpx; line-height: 42rpx; flex-shrink: 0; }


.card-tab-empty { padding: 120rpx 40rpx; text-align: center; }


.cte-title { display: block; font-size: 32rpx; font-weight: 800; color: var(--text-1); margin-bottom: 12rpx; }


.cte-desc { display: block; font-size: 26rpx; color: var(--text-3); line-height: 1.6; }


.cte-btn { margin-top: 32rpx; width: 100%; height: 96rpx; line-height: 96rpx; border-radius: 48rpx; background: var(--brand); color: #fff; font-size: 30rpx; font-weight: 800; display: flex; align-items: center; justify-content: center; padding: 0; border: 0; }


.cte-btn::after { border: 0; }


.cte-btn[disabled] { opacity: .7; }


.cte-btn-plain { background: #EEF2F5; color: #3F4650; }


.cte-secondary { display: block; margin-top: 24rpx; color: #6B7280; font-size: 26rpx; line-height: 38rpx; }




.cte-btn {
  margin-top: 32rpx; padding: 24rpx 80rpx;
  background: var(--brand); border-radius: 16rpx;
  color: #fff; font-size: 30rpx; font-weight: 700;
}

@keyframes micBorderGlow { 0%, 100% { box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), 0 10rpx 24rpx rgba(0,0,0,.22), 0 0 0 1px rgba(212,175,110,.28); } 50% { box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), 0 10rpx 26rpx rgba(0,0,0,.26), 0 0 0 1px rgba(232,202,160,.6); } }
@keyframes micBadgePulse { 0%, 100% { opacity: .85; } 50% { opacity: 1; text-shadow: 0 0 12rpx rgba(232,202,160,.9); } }

@media screen and (max-width: 340px) {
  .card-tab.member-center { padding-left: 24rpx; padding-right: 24rpx; }
  .member-identity-card { padding: 26rpx 26rpx 22rpx; }
  .mic-body { gap: 18rpx; }
  .member-level { font-size: 34rpx; }
  .member-asset-value { font-size: 34rpx; }
  .member-coupon-card { gap: 14rpx; padding: 22rpx; }
  .member-coupon-use { padding: 0 18rpx; }
}
</style>
