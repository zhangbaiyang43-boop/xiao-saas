<template>
  <view v-if="showWelcomeCoupon" class="mask welcome-mask" @click="$emit('close')">
    <view class="welcome-coupon-sheet" @click.stop>
      <text class="wc-ribbon">送你一张新人券</text>
      <view class="wc-amount-row">
        <text class="wc-currency">¥</text>
        <text class="wc-amount">{{ formatPrice(welcomeCouponData?.amount ?? welcomeCouponData?.value ?? 0) }}</text>
      </view>
      <text class="wc-cond">{{ welcomeCouponCondText }}</text>
      <view class="wc-divider"></view>
      <text class="wc-name">{{ welcomeCouponData?.name || '优惠券' }}</text>
      <view class="wc-btn" @click="$emit('go-order')"><text>去点餐使用</text></view>
      <text class="wc-skip" @click="$emit('close')">稍后再说</text>
    </view>
  </view>

  <view v-if="storeClosed || tableSessionClosed" class="closed-mask">
    <view class="closed-card">
      <view class="closed-icon-wrap"><text class="closed-icon iconfont" :class="tableSessionClosed ? 'icon-roundcheckfill' : 'icon-shopfill'"></text></view>
      <text class="closed-title">{{ tableSessionClosed ? '本桌用餐已结束' : shopName + ' 当前休息中' }}</text>
      <text class="closed-desc">{{ tableSessionClosed ? tableSessionClosedNotice : (closedNotice || '营业时间请参考门店公告') }}</text>
      <view v-if="tableSessionClosed" class="closed-btn" @click="$emit('acknowledge-closed')"><text>好的，我知道了</text></view>
      <view v-else class="closed-btn" @click="$emit('keep-browsing')"><text>仍要浏览菜单</text></view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的两个小遮罩层：新人券弹层（showWelcomeCoupon）和打烊/本桌
// 用餐结束遮罩（storeClosed || tableSessionClosed）。两个都很小、互不相关，顺手
// 放进同一个文件。纯展示组件，不带任何业务逻辑——所有点击都只 emit 出去，真正
// 的处理函数还是原来 menu.vue 里的
// closeWelcomeCoupon/goOrderFromWelcomeCoupon/acknowledgeClosedSession，一行都没有改。原模板里
// "仍要浏览菜单"按钮是直接 @click="storeClosed = false" 的状态赋值，这里改成
// emit('keep-browsing')，父组件监听后照原样赋值。
// tableSessionClosed 的「好的，我知道了」改为 emit('acknowledge-closed')：
// 父组件负责 exitDiningSession + reLaunch，不再 navigateTo 我的（避免旧 menu 留栈）。
export default {
  name: 'WelcomeCouponSheet',
  props: {
    showWelcomeCoupon: { type: Boolean, default: false },
    welcomeCouponData: { type: Object, default: null },
    welcomeCouponCondText: { type: String, default: '' },
    storeClosed: { type: Boolean, default: false },
    tableSessionClosed: { type: Boolean, default: false },
    shopName: { type: String, default: '' },
    tableSessionClosedNotice: { type: String, default: '' },
    closedNotice: { type: String, default: '' },
    // 纯格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    formatPrice: { type: Function, required: true },
  },
  emits: ['close', 'go-order', 'acknowledge-closed', 'keep-browsing'],
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';

.closed-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48rpx;
}



.closed-card {
  background: var(--bg-card);
  border-radius: 32rpx;
  padding: 56rpx 40rpx 40rpx;
  text-align: center;
  width: 100%;
}



.closed-icon-wrap {
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto 24rpx;
  border-radius: 50%;
  background: var(--bg-muted);
  color: #9aa1aa;
  display: flex;
  align-items: center;
  justify-content: center;
}



.closed-icon {
  font-size: 56rpx;
}



.closed-title {
  display: block;
  font-size: 36rpx;
  font-weight: 700;
  color: #111;
  margin-bottom: 12rpx;
}



.closed-desc {
  display: block;
  font-size: 28rpx;
  color: var(--text-3);
  line-height: 1.6;
  margin-bottom: 40rpx;
}



.closed-btn {
  padding: 24rpx 0;
  background: var(--brand);
  border-radius: 20rpx;
  text {
    font-size: 30rpx;
    color: var(--text-inverse);
    font-weight: 700;
  }
}



.welcome-mask {
  align-items: center;
  justify-content: center;
  padding: 0 48rpx;
  background: rgba(15, 23, 42, .58);
}



.welcome-coupon-sheet {
  width: 100%;
  max-width: 560rpx;
  background: linear-gradient(160deg, #ff5a3c 0%, #ff2f1f 55%, #d81717 100%);
  border: 2rpx solid rgba(255, 222, 150, 0.9);
  border-radius: 32rpx;
  padding: 48rpx 40rpx 36rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  overflow: hidden;
  box-shadow: 0 16rpx 40rpx -14rpx rgba(180, 20, 10, 0.45);
  animation: ec-card-in 0.5s cubic-bezier(0.22, 1.3, 0.4, 1) both;
}



.welcome-coupon-sheet::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg, transparent 42%, rgba(255, 255, 255, 0.5) 50%, transparent 58%);
  transform: translateX(-140%);
  animation: ec-shine 1s ease 0.45s 1;
  pointer-events: none;
}



.wc-ribbon {
  display: inline-block;
  padding: 4rpx 20rpx;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.18);
  color: #ffe9c2;
  font-size: 22rpx;
  font-weight: 700;
}



.wc-amount-row {
  display: flex;
  align-items: baseline;
  margin-top: 22rpx;
}



.wc-currency {
  font-size: 34rpx;
  font-weight: 800;
  color: var(--text-inverse);
  margin-right: 4rpx;
}



.wc-amount {
  font-size: 88rpx;
  font-weight: 900;
  color: var(--text-inverse);
  line-height: 1;
  text-shadow: 0 3rpx 0 rgba(120, 10, 0, 0.4);
}



.wc-cond {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #ffe4d2;
}



.wc-divider {
  width: 100%;
  height: 1rpx;
  background: rgba(255, 255, 255, 0.25);
  margin: 24rpx 0 18rpx;
}



.wc-name {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: var(--text-inverse);
}



.wc-btn {
  width: 100%;
  height: 88rpx;
  margin-top: 32rpx;
  border-radius: 999rpx;
  background: linear-gradient(180deg, #ffe9a8, #ffcf5c);
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  box-shadow: 0 10rpx 22rpx -10rpx rgba(255, 180, 40, 0.75);
  text { color: #7a1f00; font-size: 30rpx; font-weight: 900; }
}



.wc-skip {
  margin-top: 20rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.7);
}
</style>
