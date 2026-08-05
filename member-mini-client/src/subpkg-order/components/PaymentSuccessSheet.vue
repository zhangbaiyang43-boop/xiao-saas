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
