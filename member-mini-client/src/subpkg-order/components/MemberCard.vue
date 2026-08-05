<template>
  <scroll-view class="tab-scroll" scroll-y>
    <view v-if="bannerInfo" class="card-tab member-center">
      <view class="member-identity-card tap-shrink" @click="uni.navigateTo({ url: '/subpkg-member/pages/growth' })">
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
        <text class="member-action-title">您有{{ bannerInfo.couponCount }}张优惠券可用</text>
        <view class="member-action-btn" @click="$emit('go-order')"><text>去点餐</text></view>
      </view>

      <view v-if="usableMemberCoupons.length" class="member-section">
        <text class="member-section-title">可用优惠券</text>
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
}
</script>
