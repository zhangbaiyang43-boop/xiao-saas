<template>
  <base-overlay layer="blocking-top" @mask-click="$emit('cancel')">
    <view class="member-choice-sheet">
      <view class="member-choice-handle"></view>
      <text class="member-choice-title">{{ memberChoiceText.title }}</text>
      <text class="member-choice-desc">{{ memberChoiceText.descGeneric }}</text>

      <button
        class="member-choice-join"
        open-type="getPhoneNumber"
        :disabled="joining || ordering || paying"
        @getphonenumber="$emit('getphonenumber', $event)"
      >{{ joining ? memberChoiceText.joining : memberChoiceText.joinAction }}</button>

      <view
        class="member-choice-guest"
        :class="{ 'member-choice-guest--disabled': joining || ordering || paying }"
        @click="onGuestPay"
      >
        <text>{{ memberChoiceText.guestPayPrefix }} {{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text>
      </view>

      <text class="member-choice-join-desc">{{ memberChoiceText.joinDesc }}</text>
      <view class="member-choice-agreement">
        <text>{{ memberChoiceText.agreementPrefix }}</text>
        <text class="member-choice-agreement-link" @click.stop="$emit('open-agreement')">{{ memberChoiceText.agreementLink }}</text>
      </view>
      <text class="member-choice-privacy">{{ memberChoiceText.privacy }}</text>
    </view>
  </base-overlay>
</template>

<script>
import BaseOverlay from '@/components/base-overlay/base-overlay.vue'

// P0-A: 结算前"加入会员/直接支付"的决策层——纯展示组件，不带任何业务逻辑。
// 会员是否加入完全由顾客在这里主动选择：点"加入会员并继续"才触发手机号授权
// （由父组件 joinMemberAndCheckout 处理 join + 刷新优惠券 + 下单）；点"直接
// 支付"或点遮罩关闭都不会创建订单、不会强制注册，回到父组件已有的 guest
// 结算路径。getphonenumber 是微信小程序原生 open-type 按钮事件，这里原样
// 透传 $event，跟 CheckoutAuthSheet 的处理方式保持一致。
export default {
  name: 'MemberCheckoutChoice',
  components: { BaseOverlay },
  props: {
    memberChoiceText: { type: Object, required: true },
    confirmationText: { type: Object, required: true },
    wechatPayAmount: { type: Number, default: 0 },
    joining: { type: Boolean, default: false },
    ordering: { type: Boolean, default: false },
    paying: { type: Boolean, default: false },
  },
  emits: ['cancel', 'getphonenumber', 'guest-pay', 'open-agreement'],
  methods: {
    onGuestPay() {
      if (this.joining || this.ordering || this.paying) return
      this.$emit('guest-pay')
    },
  },
}
</script>

<style lang="scss">
.member-choice-sheet { position: absolute; left: 0; right: 0; bottom: 0; width: 100%; max-height: 60vh; background: #fff; border-radius: 32rpx 32rpx 0 0; padding: 18rpx 36rpx calc(22rpx + env(safe-area-inset-bottom)); box-sizing: border-box; display: flex; flex-direction: column; align-items: stretch; animation: memberChoiceIn .2s ease-out; }

.member-choice-handle { width: 72rpx; height: 8rpx; border-radius: 999rpx; background: #e5e7eb; align-self: center; margin-bottom: 20rpx; }

.member-choice-title { color: var(--text-1); font-size: 38rpx; font-weight: 900; text-align: center; line-height: 1.25; }

.member-choice-desc { margin-top: 12rpx; color: var(--text-2); font-size: 27rpx; line-height: 1.55; text-align: center; }

.member-choice-join { margin-top: 28rpx; height: 96rpx; border-radius: var(--radius-card); background: #16c76f; color: #fff; font-size: 31rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; box-shadow: 0 14rpx 34rpx rgba(16, 196, 105, .22); }

.member-choice-join[disabled] { opacity: .72; box-shadow: none; }

.member-choice-guest { margin-top: 18rpx; height: 88rpx; border-radius: var(--radius-card); border: 1rpx solid #dfe5e8; display: flex; align-items: center; justify-content: center; text { color: var(--text-2); font-size: 29rpx; font-weight: 800; } }

.member-choice-guest--disabled { opacity: .5; }

.member-choice-join-desc { margin-top: 20rpx; color: var(--text-3); font-size: 23rpx; line-height: 1.5; text-align: center; }

.member-choice-agreement { margin-top: 10rpx; display: flex; align-items: center; justify-content: center; gap: 4rpx; text { color: var(--text-3); font-size: 22rpx; } }

.member-choice-agreement-link { color: var(--brand); }

.member-choice-privacy { display: block; color: #a8b1bd; font-size: 21rpx; line-height: 1.45; text-align: center; margin-top: 10rpx; }

@keyframes memberChoiceIn { from { transform: translateY(24rpx); opacity: .92; } to { transform: translateY(0); opacity: 1; } }
</style>
