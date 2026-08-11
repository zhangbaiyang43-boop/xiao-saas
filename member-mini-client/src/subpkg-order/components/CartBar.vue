<template>
  <view class="cart-bar" :class="{ 'has-items': totalCount > 0 }">
    <view class="cart-main" @click="totalCount > 0 ? $emit('open-cart') : null">

      <view class="cart-icon-wrap" :class="{ 'cart-icon-wrap--pulse': cartIconPulse }">
        <text :class="['cart-iconfont', 'iconfont', totalCount > 0 ? 'icon-cartfill' : 'icon-cart']"></text>
        <view v-if="totalCount > 0" class="cart-badge" :class="{ 'cart-badge--pulse': cartBadgePulse }">
          <text>{{ cartBadgeText }}</text>
        </view>
      </view>


      <view class="cart-info">
        <template v-if="totalCount > 0">
          <text class="cart-price" :class="{ 'cart-price--highlight': amountPulse }">¥{{ formatPrice(totalPrice) }}</text>
          <text class="cart-tip">共{{ totalCount }}份</text>
        </template>
        <template v-else>
          <text class="cart-empty">未选择商品</text>
        </template>
      </view>
    </view>


    <view class="cart-right">
      <view
        class="checkout-btn"
        :class="{ disabled: totalCount === 0 }"
        @click.stop="totalCount > 0 && $emit('open-cart')"
      >
        <text>去结算</text>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的购物车悬浮条（原来是 activeTab==='order' 那段常驻底部的
// cart-bar）。纯展示组件，不带任何业务逻辑——点击都只 emit 出去，真正的处理
// 函数还是原来 menu.vue 里的 openCart，一行都没有改。v-show="activeTab==='order'"
// 这层 Tab 显隐判断留在父组件（跟 HomeTab/MemberCard 那两个 tab-scroll 包一层
// 的做法一致）。
export default {
  name: 'CartBar',
  props: {
    totalCount: { type: Number, default: 0 },
    cartIconPulse: { type: Boolean, default: false },
    cartBadgeText: { type: String, default: '' },
    cartBadgePulse: { type: Boolean, default: false },
    totalPrice: { type: Number, default: 0 },
    amountPulse: { type: Boolean, default: false },
    // 纯格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    formatPrice: { type: Function, required: true },
  },
  emits: ['open-cart'],
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';

.cart-bar {
  position: fixed;
  z-index: 320;
  bottom: calc(100rpx + env(safe-area-inset-bottom));
  left: 0;
  right: 0;
  height: calc(148rpx + env(safe-area-inset-bottom));
  min-height: calc(148rpx + env(safe-area-inset-bottom));
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 12rpx 24rpx;
  padding-bottom: calc(12rpx + env(safe-area-inset-bottom));
  background: #1f2937;
  box-shadow: 0 -6rpx 20rpx rgba(0,0,0,0.18);
  box-sizing: border-box;

  &.has-items { background: var(--text-1); }
}



.cart-main {
  flex: 1;
  min-width: 0;
  min-height: 112rpx;
  display: flex;
  align-items: center;
}



.cart-icon-wrap {
  position: relative;
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: #4B5362;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  .has-items & { background: var(--brand); }
}



.cart-iconfont {
  width: 48rpx;
  height: 48rpx;
  color: var(--text-inverse);
  font-size: 46rpx;
  line-height: 48rpx;
  text-align: center;
}



.cart-badge {
  position: absolute;
  top: -4rpx;
  right: -4rpx;
  min-width: 36rpx;
  height: 36rpx;
  border-radius: 18rpx;
  background: #F04444;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8rpx;
  box-sizing: border-box;

  text { color: var(--text-inverse); font-size: 22rpx; line-height: 36rpx; font-weight: 600; }
}



.cart-info { flex: 1; min-width: 0; margin-left: 20rpx; display: flex; flex-direction: column; justify-content: center; }


.cart-right { display: flex; align-items: center; flex-shrink: 0; }



.cart-price {
  display: block;
  color: var(--text-inverse);
  font-size: 48rpx;
  line-height: 56rpx;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.cart-tip {
  display: block;
  color: rgba(255,255,255,0.62);
  font-size: 24rpx;
  line-height: 34rpx;
  margin-top: 4rpx;
}



.cart-empty {
  display: block;
  color: rgba(255,255,255,0.72);
  font-size: 30rpx;
  line-height: 40rpx;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.checkout-btn {
  min-width: 236rpx;
  height: var(--btn-primary-height);
  padding: 0 48rpx;
  border-radius: var(--btn-primary-radius);
  background: var(--brand);
  box-shadow: 0 8rpx 24rpx rgba(7,193,96,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-sizing: border-box;

  text {
    color: var(--text-inverse);
    font-size: var(--btn-primary-font-size);
    font-weight: var(--btn-primary-font-weight);
    white-space: nowrap;
  }

  &.disabled {
    background: #4B5362;
    box-shadow: none;
    text { color: rgba(255,255,255,0.45); }
  }
}



.cart-icon-wrap {
  transform-origin: center;
  transition: background 150ms ease-out, transform 180ms ease-out;
}



.cart-icon-wrap--pulse {
  animation: cartIconPulse 180ms ease-out;
}



.cart-badge {
  transform-origin: center;
}



.cart-badge--pulse {
  animation: cartBadgePulse 180ms ease-out;
}



.cart-price {
  transform-origin: left center;
  transition: color 150ms ease-out, transform 180ms ease-out;
}



.cart-price--highlight {
  color: #34f38a;
  animation: cartAmountHighlight 200ms ease-out;
}



.checkout-btn {
  transition: background 180ms ease-out, opacity 180ms ease-out;
}

@keyframes cartIconPulse {
  0% { transform: scale(1); }
  45% { transform: scale(1.07); }
  100% { transform: scale(1); }
}

@keyframes cartBadgePulse {
  0% { opacity: .85; transform: scale(.86); }
  55% { opacity: 1; transform: scale(1.1); }
  100% { opacity: 1; transform: scale(1); }
}

@keyframes cartAmountHighlight {
  0% { transform: translateY(0); }
  45% { transform: translateY(-4rpx); }
  100% { transform: translateY(0); }
}
</style>
