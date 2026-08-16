<template>
  <view
    class="price-text"
    :class="[
      `price-text--${size}`,
      { 'price-text--pulse': pulse, 'price-text--block': block },
    ]"
  >
    <text class="price-text-currency">¥</text>
    <text class="price-text-amount">{{ displayAmount }}</text>
    <text v-if="suffix" class="price-text-suffix">{{ suffix }}</text>
  </view>
</template>

<script>
// 全站菜价展示唯一组件：¥ + 金额 + 可选后缀（起）。
// 字号用 size：md=菜卡主价，sm=行内价，lg=规格弹层价。
// 注意：微信小程序 text 不一定继承 view 的 color/font-size，字号颜色写在 text 上。
export default {
  name: 'PriceText',
  props: {
    amount: { type: [String, Number], default: '0' },
    suffix: { type: String, default: '' },
    size: { type: String, default: 'md' }, // sm | md | lg
    pulse: { type: Boolean, default: false },
    block: { type: Boolean, default: false },
  },
  computed: {
    displayAmount() {
      if (this.amount === null || this.amount === undefined || this.amount === '') return '0'
      return String(this.amount)
    },
  },
}
</script>

<style lang="scss">
.price-text {
  display: flex;
  align-items: baseline;
  min-width: 0;
  line-height: 1;
}

.price-text--block {
  flex: 1;
  overflow: hidden;
}

.price-text-currency,
.price-text-amount,
.price-text-suffix {
  color: var(--brand);
  font-weight: 700;
  line-height: 1;
}

.price-text-currency { flex-shrink: 0; }
.price-text-amount {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.price-text-suffix {
  flex-shrink: 0;
  margin-left: 2rpx;
  font-weight: 500;
}

.price-text--sm .price-text-currency { font-size: 22rpx; }
.price-text--sm .price-text-amount { font-size: 30rpx; }
.price-text--sm .price-text-suffix { font-size: 20rpx; }

.price-text--md .price-text-currency { font-size: 24rpx; }
.price-text--md .price-text-amount { font-size: 40rpx; }
.price-text--md .price-text-suffix { font-size: 22rpx; }

.price-text--lg .price-text-currency { font-size: 28rpx; }
.price-text--lg .price-text-amount { font-size: 44rpx; }
.price-text--lg .price-text-suffix { font-size: 24rpx; }

.price-text--pulse {
  animation: priceTextPulse 180ms ease-out;
}

@keyframes priceTextPulse {
  0% { transform: scale(1); }
  40% { transform: scale(1.06); }
  100% { transform: scale(1); }
}
</style>
