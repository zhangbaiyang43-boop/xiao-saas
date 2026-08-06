<template>
  <view class="mask success-mask">
    <view class="success-sheet" @click.stop>
      <view class="success-handle"></view>
      <view class="success-card">
        <view class="success-check">
          <view class="success-check-inner"></view>
        </view>
        <text class="success-title">{{ successText.title }}</text>
        <view class="success-paid-amount-row">
          <text class="success-paid-currency">{{ currency }}</text>
          <text class="success-paid-amount">{{ successTotal.toFixed(2) }}</text>
        </view>
        <text class="success-paid-label">{{ successText.paidLabel }}</text>

        <view class="order-status-bar" :class="successStatusTone">
          <text class="order-status-text">{{ successStatusText }}</text>
        </view>

        <view v-if="earnedCoupon" class="earned-coupon-card">
          <text class="ec-ribbon">{{ earnedCoupon.isSecondOrder ? '欢迎回来 · 专属奖励' : '支付成功 · 专属奖励' }}</text>
          <view class="ec-amount-row">
            <text class="ec-currency">¥</text>
            <text class="ec-amount">{{ formatPrice(earnedCoupon.amount) }}</text>
          </view>
          <text class="ec-cond">{{ earnedCoupon.threshold > 0 ? '满' + formatPrice(earnedCoupon.threshold) + '元可用' : '无门槛立减' }}</text>
          <view class="ec-divider"></view>
          <text class="ec-title">{{ (earnedCoupon.isSecondOrder ? '欢迎回来，这是你的第二次光临！再送你一张券：' : '又送你一张券：') + (earnedCoupon.name || '') }}</text>
          <text v-if="earnedCoupon.expire_time" class="ec-deadline">{{ couponValidityText(earnedCoupon) }}</text>
          <text
            v-if="couponReminderTemplateId && earnedCoupon.couponId"
            class="ec-remind-btn"
            :class="{ 'ec-remind-btn--done': reminderRequested }"
            @click="$emit('request-coupon-reminder')"
          >{{ reminderRequested ? '已设置提醒 ✓' : (requestingReminder ? '设置中...' : '提醒我别忘了用') }}</text>
        </view>

        <view class="success-summary">
          <view class="success-summary-row">
            <text class="success-summary-label">{{ successText.table }}</text>
            <text class="success-summary-value">{{ tableNo || orderModeText.unknownTable }}</text>
          </view>
          <view class="success-summary-row">
            <text class="success-summary-label">{{ successText.orderNo }}</text>
            <text class="success-summary-value">#{{ successOrderNo }}</text>
          </view>
          <view class="success-summary-row">
            <text class="success-summary-label">{{ successText.items }}</text>
            <text class="success-summary-value">{{ successOrderItemCount }}{{ successText.itemUnit }}</text>
          </view>
        </view>

        <view class="success-actions">
          <view class="success-btn-primary" @click="$emit('close-and-wait')">
            <text>{{ successText.closeAndWait }}</text>
          </view>
          <view class="success-btn-secondary" @click="$emit('continue-ordering')">
            <text>{{ successText.continueOrdering }}</text>
          </view>
          <view class="success-btn-ghost" @click="$emit('view-order-detail')">
            <text>{{ successText.viewDetail }}</text>
          </view>
        </view>

        <text class="success-safe-tip">{{ successText.safeTip }}</text>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的支付成功弹层（原来是 showSuccess 那一段模板）。纯展示组
// 件，不带任何业务逻辑——领取到的优惠券提醒、关闭并等待、继续点餐、查看订单
// 详情都只 emit 出去，真正的处理函数还是原来 menu.vue 里那几个
// （requestCouponReminder/closeSuccessAndWait/continueOrdering/
// viewOrderDetail），一行都没有改。注意：原模板的遮罩层本身没有点击关闭的
// @click，只有里面的按钮能关闭弹层，这里保持一致，没有加 mask 点击事件。
export default {
  name: 'PaymentSuccessSheet',
  props: {
    successText: { type: Object, required: true },
    currency: { type: String, default: '' },
    successTotal: { type: Number, default: 0 },
    successStatusTone: { type: String, default: '' },
    successStatusText: { type: String, default: '' },
    earnedCoupon: { type: Object, default: null },
    couponReminderTemplateId: { type: String, default: '' },
    reminderRequested: { type: Boolean, default: false },
    requestingReminder: { type: Boolean, default: false },
    tableNo: { type: [String, Number], default: '' },
    orderModeText: { type: Object, required: true },
    successOrderNo: { type: String, default: '' },
    successOrderItemCount: { type: Number, default: 0 },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    formatPrice: { type: Function, required: true },
    couponValidityText: { type: Function, required: true },
  },
  emits: ['request-coupon-reminder', 'close-and-wait', 'continue-ordering', 'view-order-detail'],
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';

.success-mask {
  align-items: center;
  justify-content: center;
  padding: 40rpx;
  background: rgba(10,16,30,0.75);
}



.success-card {
  width: 100%;
  max-height: 88vh;
  background: #fff;
  border-radius: 40rpx;
  padding: 0 0 40rpx;
  box-sizing: border-box;
  overflow-y: auto;
}



.success-check {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: var(--brand);
  margin: 0 auto 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}



.success-check-inner {
  width: 44rpx;
  height: 28rpx;
  border-left: 6rpx solid #fff;
  border-bottom: 6rpx solid #fff;
  transform: rotate(-45deg) translateY(-6rpx);
}



.success-title {
  display: block;
  font-size: 40rpx;
  font-weight: 900;
  color: var(--text-1);
  margin-bottom: 8rpx;
}


.success-paid-amount-row {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  margin: 4rpx 0 8rpx;
}


.success-paid-currency {
  font-size: 32rpx;
  font-weight: 700;
  color: #111;
  margin-bottom: 10rpx;
  margin-right: 2rpx;
}


.success-paid-amount {
  font-size: 88rpx;
  font-weight: 900;
  color: #111;
  line-height: 1;
}




.order-status-bar {
  margin: 0 40rpx 0;
  padding: 22rpx 24rpx;
  border-radius: 20rpx;
  text-align: center;
  transition: background 0.3s;
}


.order-status-text { font-size: 26rpx; font-weight: 700; color: var(--text-2); }

.order-status-bar.pending {
  background: #fef9c3;
}
.order-status-bar.preparing {
  background: var(--brand);
  animation: status-pulse 1.5s ease-in-out infinite;
}
.order-status-bar.done {
  background: #fbbf24;
}
.order-status-bar.pending .order-status-text { color: #92400e; }
.order-status-bar.preparing .order-status-text { color: #fff; font-size: 30rpx; }
.order-status-bar.done .order-status-text { color: #78350f; font-size: 30rpx; }

@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.82; }
}




.success-actions {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
  padding: 0 40rpx;
}



.success-btn-primary {
  height: 96rpx;
  border-radius: var(--radius-card);
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #fff; font-size: 34rpx; font-weight: 900; }
}


.success-btn-secondary {
  height: 96rpx;
  border-radius: var(--radius-card);
  background: #f1f5f9;
  border: 2rpx solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: var(--text-3); font-size: 30rpx; font-weight: 600; }
}



.success-btn-primary.success-btn-secondary {
  background: #f1f5f9;
  border: 2rpx solid #e2e8f0;
  text { color: var(--text-3); font-size: 30rpx; font-weight: 600; }
}


.success-btn-ghost {
  height: 80rpx;
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: var(--text-3); font-size: 28rpx; }
}



/* Order success sheet */
.success-mask {
  align-items: flex-end;
  justify-content: flex-end;
  padding: 0;
  background: rgba(15, 23, 42, .52);
}



.success-sheet {
  width: 100%;
  max-height: 88vh;
  background: #f6f7f8;
  border-radius: 32rpx 32rpx 0 0;
  padding: 18rpx 24rpx calc(20rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  animation: successSheetIn 200ms ease-out;
}



.success-handle {
  width: 72rpx;
  height: 8rpx;
  border-radius: 999rpx;
  background: #d7dce2;
  margin: 0 auto 18rpx;
}



.success-sheet .success-card {
  max-height: none;
  overflow: visible;
  border-radius: 28rpx;
  padding: 44rpx 34rpx 28rpx;
  border: 1rpx solid #edf0f2;
  text-align: center;
}



.success-sheet .success-check {
  width: 112rpx;
  height: 112rpx;
  margin: 0 auto 22rpx;
  box-shadow: 0 12rpx 28rpx rgba(16,196,105,.22);
  animation: successCheckIn 280ms ease-out;
}



.success-sheet .success-check-inner {
  width: 46rpx;
  height: 28rpx;
  border-left: 7rpx solid #fff;
  border-bottom: 7rpx solid #fff;
  transform: rotate(-45deg) translateY(-6rpx);
}



.success-sheet .success-title {
  margin: 0;
  font-size: 46rpx;
  line-height: 1.2;
  font-weight: 900;
  color: var(--text-1);
}



.success-sheet .success-paid-amount-row {
  margin: 12rpx 0 0;
}



.success-sheet .success-paid-currency {
  font-size: 34rpx;
  margin-bottom: 10rpx;
}



.success-sheet .success-paid-amount {
  font-size: 68rpx;
  letter-spacing: 0;
}



.success-paid-label {
  display: block;
  margin-top: 4rpx;
  color: var(--text-3);
  font-size: 23rpx;
}



.success-sheet .order-status-bar {
  margin: 28rpx 0 0;
  padding: 22rpx 24rpx;
  border-radius: 20rpx;
  background: #ecfbf3;
  text-align: center;
  animation: none;
}



.success-sheet .order-status-text {
  color: var(--brand);
  font-size: 27rpx;
  font-weight: 800;
  line-height: 1.55;
}

.success-sheet .order-status-bar.pending,
.success-sheet .order-status-bar.preparing {
  background: #ecfbf3;
}

.success-sheet .order-status-bar.done {
  background: #f0fdf4;
}

.success-sheet .order-status-bar.warning {
  background: #fff7ed;
}

.success-sheet .order-status-bar.warning .order-status-text {
  color: #9a6a21;
}



.earned-coupon-card {
  position: relative;
  margin-top: 20rpx;
  padding: 34rpx 28rpx 28rpx;
  border-radius: 24rpx;
  text-align: center;
  background: linear-gradient(160deg, #ff5a3c 0%, #ff2f1f 55%, #d81717 100%);
  border: 2rpx solid rgba(255, 222, 150, 0.9);
  box-shadow: 0 16rpx 40rpx -14rpx rgba(180, 20, 10, 0.45);
  overflow: hidden;
  animation: ec-card-in 0.5s cubic-bezier(0.22, 1.3, 0.4, 1) both;
}



.earned-coupon-card::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg, transparent 42%, rgba(255, 255, 255, 0.5) 50%, transparent 58%);
  transform: translateX(-140%);
  animation: ec-shine 1s ease 0.45s 1;
  pointer-events: none;
}



.ec-ribbon {
  display: inline-block;
  padding: 4rpx 20rpx;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.18);
  color: #ffe9c2;
  font-size: 21rpx;
  font-weight: 700;
  margin-bottom: 14rpx;
}



.ec-amount-row {
  display: flex;
  align-items: baseline;
  justify-content: center;
}



.ec-currency {
  font-size: 30rpx;
  font-weight: 800;
  color: #ffffff;
  margin-right: 2rpx;
}



.ec-amount {
  font-size: 68rpx;
  font-weight: 900;
  color: #ffffff;
  line-height: 1;
  text-shadow: 0 3rpx 0 rgba(120, 10, 0, 0.4);
}



.ec-cond {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #ffe4d2;
}



.ec-divider {
  width: 100%;
  height: 1rpx;
  background: rgba(255, 255, 255, 0.25);
  margin: 20rpx 0 18rpx;
}



.ec-title {
  display: block;
  font-size: 25rpx;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.5;
}



.ec-deadline {
  display: block;
  margin-top: 8rpx;
  font-size: 21rpx;
  font-weight: 700;
  color: #ffe9c2;
}



.ec-remind-btn {
  display: inline-block;
  margin-top: 18rpx;
  padding: 8rpx 22rpx;
  border: 1rpx solid rgba(255, 255, 255, 0.6);
  border-radius: 999rpx;
  font-size: 21rpx;
  font-weight: 700;
  color: #ffffff;
  background: rgba(255, 255, 255, 0.12);
}



.ec-remind-btn--done {
  border-color: rgba(255, 255, 255, 0.3);
  color: rgba(255, 255, 255, 0.55);
  background: transparent;
}



.success-summary {
  margin-top: 26rpx;
  padding-top: 4rpx;
}



.success-summary-row {
  min-height: 76rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1rpx solid #edf0f2;
  gap: 24rpx;
}



.success-summary-row:last-child {
  border-bottom: 0;
}



.success-summary-label {
  color: var(--text-3);
  font-size: 27rpx;
}



.success-summary-value {
  color: var(--text-1);
  font-size: 29rpx;
  font-weight: 800;
  text-align: right;
  max-width: 440rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.success-sheet .success-actions {
  margin-top: 24rpx;
  padding: 0;
  gap: 14rpx;
}



.success-sheet .success-btn-primary {
  height: 98rpx;
  border-radius: var(--radius-card);
  background: var(--brand);
  box-shadow: 0 12rpx 24rpx rgba(16,196,105,.18);
}



.success-sheet .success-btn-primary text {
  color: #fff;
  font-size: 32rpx;
  font-weight: 900;
}



.success-sheet .success-btn-secondary {
  height: 94rpx;
  border-radius: var(--radius-card);
  background: #fff;
  border: 1rpx solid #dfe5e8;
}



.success-sheet .success-btn-secondary text {
  color: #344054;
  font-size: 30rpx;
  font-weight: 800;
}



.success-sheet .success-btn-ghost {
  height: 68rpx;
}



.success-sheet .success-btn-ghost text {
  color: var(--text-2);
  font-size: 26rpx;
  font-weight: 700;
}



.success-safe-tip {
  display: block;
  margin: 16rpx 10rpx 0;
  color: var(--text-3);
  font-size: 22rpx;
  line-height: 1.55;
}

@keyframes successSheetIn {
  from { transform: translateY(28rpx); opacity: .92; }
  to { transform: translateY(0); opacity: 1; }
}

@keyframes successCheckIn {
  0% { transform: scale(.82); opacity: 0; }
  70% { transform: scale(1.04); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .success-sheet,
  .success-sheet .success-check {
    animation: none;
  }
}
</style>
