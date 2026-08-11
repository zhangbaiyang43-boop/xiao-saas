<template>
  <view v-if="couponBarVisible" class="coupon-bar tap-shrink" @click="$emit('open-coupon-picker')">
    <text class="coupon-bar-icon iconfont icon-youhuiquan"></text>
    <text class="coupon-bar-text">{{ couponBarPrefix }}<text class="coupon-bar-amount">{{ couponBarAmount }}</text></text>
    <text class="coupon-bar-arrow iconfont icon-roundright"></text>
  </view>
  <button
    v-else-if="!isCustomerLoggedIn && newCustomerCouponPreview"
    class="coupon-bar new-customer-bar tap-shrink"
    open-type="getPhoneNumber"
    :disabled="memberAuthorizing"
    @getphonenumber="$emit('phone-auth', $event)"
  >
    <text class="coupon-bar-icon iconfont icon-youhuiquan"></text>
    <text class="coupon-bar-text">{{ newCustomerHookText }}</text>
    <text class="coupon-bar-arrow iconfont icon-roundright"></text>
  </button>

  <view
    v-if="couponNudgeState.visible"
    class="coupon-nudge-bar"
    :class="{ 'coupon-nudge-bar--done': couponNudgeState.satisfied }"
  >
    <view class="coupon-nudge-main" @click="couponNudgeState.satisfied ? $emit('open-coupon-picker') : $emit('coupon-add-on')">
      <text class="coupon-nudge-icon iconfont icon-youhuiquan"></text>
      <view class="coupon-nudge-copy">
        <template v-if="couponNudgeState.satisfied">
          <text class="coupon-nudge-title">已享满{{ couponNudgeState.thresholdText }}减{{ couponNudgeState.discountText }}优惠</text>
        </template>
        <template v-else>
          <text class="coupon-nudge-title">再加 <text class="coupon-nudge-strong">¥{{ couponNudgeState.diffText }}</text>，立享满{{ couponNudgeState.thresholdText }}减{{ couponNudgeState.discountText }}</text>
        </template>
        <text class="coupon-nudge-sub">当前 ¥{{ formatPrice(totalPrice) }} / 门槛 ¥{{ couponNudgeState.thresholdText }}</text>
      </view>
    </view>
    <view v-if="!couponNudgeState.satisfied" class="coupon-nudge-action" @click="$emit('coupon-add-on')">
      <text>去凑单</text>
    </view>
    <view v-else class="coupon-nudge-action coupon-nudge-action--plain" @click="$emit('open-coupon-picker')">
      <text>换券</text>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的优惠券横幅（顶部满减/新人券横幅）+ 凑单提醒条（原来是
// activeTab==='order' 那两段模板）。纯展示组件，不带任何业务逻辑——所有点击都
// 只 emit 出去，真正的处理函数还是原来 menu.vue 里的
// openCouponPicker/handleMemberCardAuth/goCouponAddOn，一行都没有改。
// v-if="activeTab==='order'" 这层 Tab 显隐判断留在父组件（用一个 v-if 包住这个
// 组件整体，因为原来两段模板本来就都用 v-if 直接从 DOM 移除，不是 v-show）。
export default {
  name: 'CouponBar',
  props: {
    couponBarVisible: { type: Boolean, default: false },
    couponBarPrefix: { type: String, default: '' },
    couponBarAmount: { type: String, default: '' },
    isCustomerLoggedIn: { type: Boolean, default: false },
    newCustomerCouponPreview: { type: Object, default: null },
    newCustomerHookText: { type: String, default: '' },
    memberAuthorizing: { type: Boolean, default: false },
    couponNudgeState: { type: Object, required: true },
    totalPrice: { type: Number, default: 0 },
    // 纯格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    formatPrice: { type: Function, required: true },
  },
  emits: ['open-coupon-picker', 'phone-auth', 'coupon-add-on'],
}
</script>

<style lang="scss">
.coupon-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10rpx;
  height: 68rpx;
  padding: 0 32rpx;
  background: linear-gradient(90deg, #fdf0dc, #fbe4bf);
  box-sizing: border-box;
}



.coupon-bar-icon {
  font-size: 26rpx;
  line-height: 1;
  color: #b5691f;
}



.coupon-bar-text {
  flex: 1;
  min-width: 0;
  font-size: 24rpx;
  font-weight: 700;
  color: #5a3c1e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.coupon-bar-amount {
  color: #e0432a;
  font-weight: 800;
}



.coupon-bar-arrow {
  flex-shrink: 0;
  color: rgba(90, 60, 30, 0.55);
  font-size: 24rpx;
  line-height: 1;
}



.new-customer-bar {
  width: 100%;
  margin: 0;
  border: 0;
  border-radius: 0;
  line-height: normal;
}


.new-customer-bar::after { border: none; }


.new-customer-bar[disabled] { opacity: .7; }




.coupon-nudge-bar {
  position: fixed;
  left: 20rpx;
  right: 20rpx;
  bottom: calc(248rpx + env(safe-area-inset-bottom) + env(safe-area-inset-bottom));
  z-index: 319;
  min-height: 76rpx;
  padding: 12rpx 14rpx 12rpx 18rpx;
  border-radius: 18rpx 18rpx 0 0;
  background: #fff7e6;
  border: 1rpx solid #ffe2ad;
  box-shadow: 0 -6rpx 18rpx rgba(120, 75, 20, .08);
  display: flex;
  align-items: center;
  gap: 14rpx;
  box-sizing: border-box;
}



.coupon-nudge-bar--done {
  background: #ecfbf3;
  border-color: #bdebd2;
}



.coupon-nudge-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12rpx;
}



.coupon-nudge-icon {
  flex-shrink: 0;
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  background: #ffe9c7;
  color: #d85a22;
  font-size: 24rpx;
  line-height: 42rpx;
  text-align: center;
}



.coupon-nudge-bar--done .coupon-nudge-icon {
  background: #dff7e9;
  color: var(--brand);
}



.coupon-nudge-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}



.coupon-nudge-title {
  color: #5a3c1e;
  font-size: 25rpx;
  line-height: 34rpx;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.coupon-nudge-bar--done .coupon-nudge-title {
  color: #0f8f50;
}



.coupon-nudge-strong {
  color: #ef3f24;
  font-weight: 900;
}



.coupon-nudge-sub {
  margin-top: 2rpx;
  color: #9a6a21;
  font-size: 20rpx;
  line-height: 28rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.coupon-nudge-bar--done .coupon-nudge-sub {
  color: #43a36b;
}



.coupon-nudge-action {
  flex-shrink: 0;
  height: 52rpx;
  min-width: 112rpx;
  padding: 0 20rpx;
  border-radius: 26rpx;
  background: #ff5a3c;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}



.coupon-nudge-action text {
  color: var(--text-inverse);
  font-size: 23rpx;
  line-height: 32rpx;
  font-weight: 900;
  white-space: nowrap;
}



.coupon-nudge-action--plain {
  background: var(--brand);
}
</style>
