<template>
  <view class="mask checkout-auth-mask" @click="$emit('cancel')">
    <view class="checkout-auth-sheet" @click.stop>
      <view class="checkout-auth-handle"></view>
      <text class="checkout-auth-title">{{ authSheetText.title }}</text>
      <text class="checkout-auth-desc">{{ authSheetText.desc }}</text>
      <view class="checkout-auth-order">
        <view class="checkout-auth-row"><text>{{ authSheetText.store }}</text><text>{{ shopName }}</text></view>
        <view class="checkout-auth-row"><text>{{ authSheetText.table }}</text><text>{{ tableNo || authSheetText.unknownTable }}</text></view>
        <view class="checkout-auth-row checkout-auth-row--amount"><text>{{ authAmountLabel }}</text><text>{{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text></view>
      </view>
      <view class="checkout-auth-auto">
        <text>{{ authSheetText.auto }}</text>
      </view>
      <button
        class="checkout-auth-primary"
        open-type="getPhoneNumber"
        :disabled="authorizing || ordering || paying"
        @getphonenumber="$emit('getphonenumber', $event)"
      >{{ authPrimaryText }}</button>
      <view class="checkout-auth-cancel" @click="$emit('cancel')">
        <text>{{ authSheetText.cancel }}</text>
      </view>
      <text class="checkout-auth-member">{{ authSheetText.member }}</text>
      <text class="checkout-auth-privacy">{{ authSheetText.privacy }}</text>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的结算前手机号授权弹层（原来是 showCheckoutAuth 那一段模
// 板）。纯展示组件，不带任何业务逻辑——取消、微信手机号授权都只 emit 出去，
// 真正的处理函数还是原来 menu.vue 里的 cancelCheckoutAuth/handleCheckoutAuth，
// 一行都没有改。getphonenumber 是微信小程序原生 open-type 按钮事件，这里原样
// 透传 $event，不做任何包装或改造，保证 event.detail.code 等字段跟之前完全
// 一致。
export default {
  name: 'CheckoutAuthSheet',
  props: {
    authSheetText: { type: Object, required: true },
    shopName: { type: String, default: '' },
    tableNo: { type: [String, Number], default: '' },
    authAmountLabel: { type: String, default: '' },
    confirmationText: { type: Object, required: true },
    wechatPayAmount: { type: Number, default: 0 },
    authorizing: { type: Boolean, default: false },
    ordering: { type: Boolean, default: false },
    paying: { type: Boolean, default: false },
    authPrimaryText: { type: String, default: '' },
  },
  emits: ['cancel', 'getphonenumber'],
}
</script>

<style lang="scss">
.checkout-auth-mask { align-items: flex-end; }


.checkout-auth-sheet { width: 100%; max-height: 55vh; background: #fff; border-radius: 32rpx 32rpx 0 0; padding: 18rpx 36rpx calc(22rpx + env(safe-area-inset-bottom)); box-sizing: border-box; display: flex; flex-direction: column; align-items: stretch; animation: authSheetIn .2s ease-out; }


.checkout-auth-handle { width: 72rpx; height: 8rpx; border-radius: 999rpx; background: #e5e7eb; align-self: center; margin-bottom: 20rpx; }


.checkout-auth-title { color: var(--text-1); font-size: 38rpx; font-weight: 900; text-align: center; line-height: 1.25; }


.checkout-auth-desc { margin-top: 12rpx; color: var(--text-2); font-size: 27rpx; line-height: 1.55; text-align: center; }


.checkout-auth-order { margin-top: 22rpx; padding: 22rpx 24rpx; border-radius: 22rpx; background: #f8fafb; border: 1rpx solid #edf0f2; }


.checkout-auth-row { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; color: var(--text-3); font-size: 26rpx; line-height: 1.5; }


.checkout-auth-row + .checkout-auth-row { margin-top: 12rpx; }


.checkout-auth-row text:last-child { color: var(--text-1); font-weight: 800; text-align: right; max-width: 440rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.checkout-auth-row--amount text:last-child { color: var(--brand); font-size: 32rpx; font-weight: 900; }


.checkout-auth-auto { margin-top: 18rpx; padding: 18rpx 20rpx; border-radius: 18rpx; background: #ecfbf3; color: #0f8f50; font-size: 24rpx; line-height: 1.55; }


.checkout-auth-primary { margin-top: 24rpx; height: 96rpx; border-radius: var(--radius-card); background: #16c76f; color: #fff; font-size: 31rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; box-shadow: 0 14rpx 34rpx rgba(16, 196, 105, .22); }


.checkout-auth-primary[disabled] { opacity: .72; box-shadow: none; }


.checkout-auth-cancel { height: 72rpx; display: flex; align-items: center; justify-content: center; color: var(--text-3); font-size: 28rpx; }


.checkout-auth-member { display: block; color: var(--text-3); font-size: 22rpx; line-height: 1.45; text-align: center; margin-top: 2rpx; }


.checkout-auth-privacy { display: block; color: #a8b1bd; font-size: 21rpx; line-height: 1.45; text-align: center; margin-top: 10rpx; }
</style>
