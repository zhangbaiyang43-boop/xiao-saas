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
