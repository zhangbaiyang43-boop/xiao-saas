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
        <text class="success-paid-label">{{ paidLabel }}</text>

        <view class="order-status-bar" :class="successStatusTone">
          <text class="order-status-text">{{ successStatusText }}</text>
          <text class="order-status-hint">状态自动更新 · 请勿重复提交或支付</text>
        </view>

        <view v-if="pickupNoEnabled && !pickupNo" class="pickup-pending">
          <text class="pickup-pending-title">桌牌待领取</text>
          <text class="pickup-pending-tip">请向工作人员领取桌牌</text>
        </view>

        <view v-if="earnedCoupon" class="reward-coupon">
          <template v-if="pickupNoEnabled && !pickupNo">
            <text class="reward-coupon-text">已获券 ¥{{ formatPrice(earnedCoupon.amount) }}</text>
            <text
              v-if="couponReminderTemplateId && earnedCoupon.couponId"
              class="reward-coupon-remind"
              :class="{ 'reward-coupon-remind--done': reminderRequested }"
              @click="$emit('request-coupon-reminder')"
            >{{ reminderRequested ? '已提醒 ✓' : (requestingReminder ? '设置中...' : '提醒我') }}</text>
          </template>
          <template v-else>
            <text class="reward-coupon-text">已获优惠券 ¥{{ formatPrice(earnedCoupon.amount) }}{{ earnedCoupon.threshold > 0 ? ' · 满' + formatPrice(earnedCoupon.threshold) + '元可用' : ' · 无门槛' }}</text>
            <text
              v-if="couponReminderTemplateId && earnedCoupon.couponId"
              class="reward-coupon-remind"
              :class="{ 'reward-coupon-remind--done': reminderRequested }"
              @click="$emit('request-coupon-reminder')"
            >{{ reminderRequested ? '已设置提醒 ✓' : (requestingReminder ? '设置中...' : '提醒我别忘了用') }}</text>
          </template>
        </view>

        <!-- P0-B2a: 会员数字唯一 authority 是 memberValue.status === 'available'；
             合法的 0 值（真的没省钱/没积分）不展示、不误判为异常。 -->
        <view
          v-if="memberValue && memberValue.status === 'available' && (memberValue.member_savings > 0 || memberValue.points_earned > 0)"
          class="success-reward-line"
        >
          <text v-if="memberValue.member_savings > 0">会员本单省 ¥{{ formatPrice(memberValue.member_savings) }}</text>
          <text v-if="memberValue.member_savings > 0 && memberValue.points_earned > 0"> · +{{ memberValue.points_earned }}积分</text>
          <text v-if="!(memberValue.member_savings > 0) && memberValue.points_earned > 0">本单 +{{ memberValue.points_earned }}积分</text>
        </view>

        <view class="success-summary">
          <view class="success-summary-row">
            <text class="success-summary-label">{{ successText.table }}</text>
            <text class="success-summary-value">{{ tableNo || orderModeText.unknownTable }}</text>
          </view>
          <view v-if="pickupNoEnabled && pickupNo" class="success-summary-row">
            <text class="success-summary-label">桌牌</text>
            <text class="success-summary-value">{{ pickupNo }} 号</text>
          </view>
        </view>

        <view class="success-actions">
          <view class="success-btn-primary" @click="$emit('view-order-detail')">
            <text>{{ successText.viewDetail }}</text>
          </view>
          <view class="success-btn-secondary" @click="$emit('continue-ordering')">
            <text>{{ successText.continueOrdering }}</text>
          </view>
          <view class="success-btn-ghost" @click="$emit('close-and-wait')">
            <text>关闭</text>
          </view>
        </view>
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
    // postpay/table_account 下单成功时没有实际收款，不能沿用 successText.paidLabel
    // 那句"实付金额"——调用方（useSuccessSheetView.js）按这一笔订单自己的
    // payment_mode 算出该用哪句话，这里只负责渲染，不判断该显示哪句。
    paidLabel: { type: String, required: true },
    currency: { type: String, default: '' },
    successTotal: { type: Number, default: 0 },
    successStatusTone: { type: String, default: '' },
    successStatusText: { type: String, default: '' },
    // P0-B2a: GET /v1/orders/my 的 member_value 权威结果，display-only——
    // 组件只按 status/member_savings/points_earned/points_balance 判断展示
    // 与否，不在这里计算、请求或猜测任何数值。
    memberValue: { type: Object, default: null },
    earnedCoupon: { type: Object, default: null },
    couponReminderTemplateId: { type: String, default: '' },
    reminderRequested: { type: Boolean, default: false },
    requestingReminder: { type: Boolean, default: false },
    tableNo: { type: [String, Number], default: '' },
    pickupNoEnabled: { type: Boolean, default: false },
    pickupNo: { type: [String, Number], default: '' },
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
  background: var(--bg-card);
  border-radius: 40rpx;
  padding: 0 0 40rpx;
  box-sizing: border-box;
  overflow-y: auto;
}



.pickup-pending {
  margin: 16rpx 0 0;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  background: #fff7ed;
  border: 1rpx solid #fde7cf;
  text-align: center;
}
.pickup-pending-title {
  display: block;
  font-size: 27rpx;
  font-weight: 800;
  color: #9a3412;
}
.pickup-pending-tip {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #9a6a21;
  line-height: 1.4;
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
.order-status-bar.preparing .order-status-text { color: var(--text-inverse); font-size: 30rpx; }
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
  text { color: var(--text-inverse); font-size: 34rpx; font-weight: 900; }
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
  background: var(--bg-subtle);
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
  width: 96rpx;
  height: 96rpx;
  margin: 0 auto 16rpx;
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
  font-size: 40rpx;
  line-height: 1.2;
  font-weight: 900;
  color: var(--text-1);
}



.success-sheet .success-paid-amount-row {
  margin: 8rpx 0 0;
}



.success-sheet .success-paid-currency {
  font-size: 30rpx;
  margin-bottom: 8rpx;
}



.success-sheet .success-paid-amount {
  font-size: 52rpx;
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

.success-sheet .order-status-text {
  display: block;
}

.order-status-hint {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  font-weight: 400;
  line-height: 1.4;
  color: var(--text-3);
}

.success-sheet .order-status-bar.warning .order-status-hint {
  color: #b08636;
}



.success-reward-line {
  display: block;
  margin-top: 16rpx;
  font-size: 23rpx;
  color: var(--text-3);
  line-height: 1.5;
}



.reward-coupon {
  margin-top: 14rpx;
  padding: 16rpx 20rpx;
  border-radius: 16rpx;
  background: #f6f7f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
}

.reward-coupon-text {
  flex: 1;
  text-align: left;
  font-size: 23rpx;
  font-weight: 700;
  color: var(--text-2);
  line-height: 1.4;
}

.reward-coupon-remind {
  flex: none;
  padding: 8rpx 20rpx;
  border-radius: 999rpx;
  border: 1rpx solid #d7dce2;
  font-size: 21rpx;
  font-weight: 700;
  color: var(--text-2);
  background: var(--bg-card);
}

.reward-coupon-remind--done {
  border-color: #e2e6ea;
  color: var(--text-3);
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
}



.success-sheet .success-btn-primary text {
  color: var(--text-inverse);
  font-size: 32rpx;
  font-weight: 900;
}



.success-sheet .success-btn-secondary {
  height: 94rpx;
  border-radius: var(--radius-card);
  background: var(--bg-card);
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
