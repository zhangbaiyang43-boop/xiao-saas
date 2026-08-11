<template>
  <view class="mask" @click="$emit('close')">
    <view class="cart-sheet order-confirm-sheet" @click.stop>
      <view class="order-confirm-head">
        <text class="order-confirm-title">{{ confirmationText.title }}</text>
        <text class="order-confirm-close iconfont icon-close" @click="$emit('close')"></text>
      </view>

      <scroll-view class="order-confirm-content" scroll-y>
        <view class="order-summary-card" :class="{ 'order-summary-card--missing': !tableNo }" @click="$emit('show-table-hint')">
          <view class="summary-mode-pill"><text>{{ orderModeText.dineIn }}</text></view>
          <text class="summary-table-no">{{ (tableNo || orderModeText.unknownTable) + '桌' }}</text>
          <text v-if="!tableNo" class="summary-table-tip">{{ confirmationText.tableMissing }}</text>
        </view>

        <view
          v-if="memberSummaryText"
          class="member-summary-card"
          :class="{ 'member-summary-card--member': isMember, 'member-summary-card--guest': !isMember }"
        >
          <text class="member-summary-text">{{ memberSummaryText }}</text>
        </view>

        <view class="confirm-card selected-items-section">
          <view class="selected-items-summary" @click="$emit('toggle-items-expanded')">
            <view class="selected-items-title-wrap">
              <view class="confirm-title-line"><text class="confirm-title-icon iconfont icon-list"></text><text class="selected-items-title">{{ confirmationText.selectedItems }}({{ totalCount }})</text></view>
            </view>
            <view class="selected-items-action">
              <text class="selected-items-amount">{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text>
              <text :class="['selected-items-toggle-icon', 'iconfont', itemsExpanded ? 'icon-pullup' : 'icon-unfold']"></text>
            </view>
          </view>
          <view v-if="itemsExpanded" class="cart-items-panel">
            <scroll-view class="cart-items" scroll-y>
              <view v-for="item in cartItems" :key="item.specKey || item.id" class="cart-row">
                <view class="cart-row-main">
                  <text class="cart-row-name">{{ item.name }}</text>
                  <text v-if="item.specLabel" class="cart-row-spec">{{ item.specLabel }}</text>
                </view>
                <view class="cart-row-right">
                  <view class="counter-btn minus sm" @click="$emit('remove-from-cart', item)"><text class="iconfont icon-move"></text></view>
                  <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === (item.specKey || item.id) }">{{ item.qty }}</text>
                  <add-btn size="sm" @click="$emit('increase-cart-item', item)" />
                  <text class="cart-row-price">{{ confirmationText.currency }}{{ (item.price * item.qty).toFixed(2) }}</text>
                </view>
              </view>
            </scroll-view>
            <view class="cart-clear-line" @click="$emit('clear-cart')">
              <text class="iconfont icon-delete"></text>
              <text>{{ confirmationText.clear }}</text>
            </view>
          </view>
        </view>

        <view class="confirm-card order-preference-section">
          <view class="remark-summary-row" @click="$emit('toggle-order-remark-expanded')">
            <view class="remark-label-wrap"><text class="remark-label-icon iconfont icon-edit"></text><text class="remark-label">{{ confirmationText.orderRemark }}</text></view>
            <view class="remark-summary-action">
              <text class="remark-summary-text">{{ orderRemarkSummary }}</text>
              <text :class="['remark-summary-toggle-icon', 'iconfont', orderRemarkExpanded ? 'icon-pullup' : 'icon-unfold']"></text>
            </view>
          </view>
          <view v-if="orderRemarkExpanded && orderRemarkChips.length" class="remark-chips">
            <view
              v-for="chip in orderRemarkChips"
              :key="chip"
              class="remark-chip"
              :class="{ 'remark-chip--on': remark.includes(chip) }"
              @click="$emit('toggle-remark-chip', chip)"
            ><text>{{ chip }}</text></view>
          </view>
          <view v-if="orderRemarkExpanded" class="remark-row order-remark-row">
            <text v-if="!showOrderRemarkExtra" class="item-remark-extra-toggle" @click="$emit('show-order-remark-extra')">+ 其他要求</text>
            <input v-else class="remark-input" v-model="remarkModel" :placeholder="confirmationText.orderRemarkPlaceholder" placeholder-class="remark-placeholder" maxlength="60" />
          </view>
        </view>

        <view class="confirm-card price-summary-card">
          <view class="price-row"><view class="price-label-wrap"><text class="price-label-icon iconfont icon-list"></text><text>{{ confirmationText.goodsAmount }}</text></view><text>{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text></view>
          <view class="price-row price-row--clickable" @click="$emit('open-coupon-picker')">
            <view class="price-label-wrap"><text class="price-label-icon iconfont icon-ticket"></text><text>{{ confirmationText.coupon }}</text></view>
            <text v-if="discountAmount > 0" class="price-discount">-{{ confirmationText.currency }}{{ discountAmount.toFixed(2) }} {{ confirmationText.arrow }}</text>
            <text v-else-if="availableCoupons.length > 0" class="price-muted">{{ availableCoupons.length }}{{ confirmationText.couponAvailable }} {{ confirmationText.arrow }}</text>
            <text v-else class="price-muted">{{ confirmationText.couponNone }} {{ confirmationText.arrow }}</text>
          </view>
          <view class="price-row price-row--payable">
            <view class="price-label-wrap"><text class="price-label-icon iconfont icon-pay"></text><text>{{ confirmPaymentLabel }}</text></view>
            <text>{{ confirmationText.currency }}{{ wechatPayAmount.toFixed(2) }}</text>
          </view>
        </view>
      </scroll-view>

      <view class="order-confirm-bottom">
        <view class="checkout-btn-full" :class="{ 'checkout-btn-full--disabled': !canSubmitOrder || ordering || paying }" @click="$emit('checkout')">
          <text class="checkout-btn-icon iconfont icon-pay"></text><text>{{ payButtonText }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的购物车/结算确认弹层（原来是 showCart 那一段模板）。纯展
// 示组件，不带任何业务逻辑——所有需要改父组件状态的动作（关闭、桌台提示、展开
// /收起已选菜品、加减数量、清空购物车、备注展开/切换/输入、打开优惠券选择器、
// 提交结算）都只 emit 出去，真正的处理函数还是原来 menu.vue 里那几个
// （closeOrderConfirm/showTableHint/toggleItemsExpanded/removeFromCart/
// increaseCartItem/clearCart/toggleOrderRemarkExpanded/toggleRemarkChip/
// openCouponPicker/goCheckout），一行都没有改。CouponPicker 本身仍然是
// menu.vue 里的兄弟组件（因为顶部优惠券横幅等其它入口也会打开它），这里只负责
// emit 打开事件，不拥有 showCouponPicker 状态。
import AddBtn from './AddBtn.vue'

export default {
  name: 'CheckoutSheet',
  components: { AddBtn },
  props: {
    confirmationText: { type: Object, required: true },
    orderModeText: { type: Object, required: true },
    tableNo: { type: [String, Number], default: '' },
    itemsExpanded: { type: Boolean, default: false },
    cartItems: { type: Array, default: () => [] },
    totalCount: { type: Number, default: 0 },
    totalPrice: { type: Number, default: 0 },
    qtyPulseKey: { type: String, default: '' },
    orderRemarkExpanded: { type: Boolean, default: false },
    orderRemarkSummary: { type: String, default: '' },
    orderRemarkChips: { type: Array, default: () => [] },
    remark: { type: String, default: '' },
    showOrderRemarkExtra: { type: Boolean, default: false },
    discountAmount: { type: Number, default: 0 },
    availableCoupons: { type: Array, default: () => [] },
    confirmPaymentLabel: { type: String, default: '' },
    wechatPayAmount: { type: Number, default: 0 },
    expectedPoints: { type: Number, default: 0 },
    isMember: { type: Boolean, default: false },
    isLoggedIn: { type: Boolean, default: false },
    memberLevelLabel: { type: String, default: '' },
    memberSummaryText: { type: String, default: '' },
    canSubmitOrder: { type: Boolean, default: false },
    ordering: { type: Boolean, default: false },
    paying: { type: Boolean, default: false },
    payButtonText: { type: String, default: '' },
  },
  emits: [
    'close',
    'show-table-hint',
    'toggle-items-expanded',
    'remove-from-cart',
    'increase-cart-item',
    'clear-cart',
    'toggle-order-remark-expanded',
    'toggle-remark-chip',
    'show-order-remark-extra',
    'update:remark',
    'open-coupon-picker',
    'checkout',
  ],
  computed: {
    remarkModel: {
      get() { return this.remark },
      set(v) { this.$emit('update:remark', v) },
    },
  },
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';

.cart-sheet {
  width: 100%;
  background: #f5f7f8;
  border-radius: 32rpx 32rpx 0 0;
  box-sizing: border-box;
  max-height: 88vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.order-confirm-head { flex-shrink: 0; display: grid; grid-template-columns: 1fr 64rpx; align-items: center; padding: 30rpx 28rpx 22rpx; background: var(--bg-card); border-bottom: 1rpx solid #edf0f2; }


.order-confirm-title { font-size: 36rpx; font-weight: 900; color: var(--text-1); }


.order-confirm-close { width: 64rpx; height: 64rpx; display: flex; align-items: center; justify-content: center; color: var(--text-3); font-size: 34rpx; line-height: 64rpx; text-align: center; }


.order-confirm-content { flex: 1; min-height: 0; padding: 20rpx 24rpx 18rpx; box-sizing: border-box; }


.order-confirm-bottom { flex-shrink: 0; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: rgba(255,255,255,0.96); border-top: 1rpx solid #edf0f2; }


.order-summary-card { padding: 18rpx 24rpx; border-radius: var(--radius-card); background: #ecfbf3; border: 1rpx solid #cbeedb; margin-bottom: 18rpx; display: flex; align-items: center; gap: 14rpx; }


.order-summary-card--missing { background: #fff7ed; border-color: #fed7aa; }


.member-summary-card {
  padding: 16rpx 24rpx;
  border-radius: var(--radius-card);
  margin-bottom: 18rpx;
  display: flex;
  align-items: center;
  min-height: 56rpx;
  box-sizing: border-box;
}


.member-summary-card--member {
  background: #f0f7ff;
  border: 1rpx solid #d6e8ff;
}


.member-summary-card--guest {
  background: #f8fafc;
  border: 1rpx solid #e8edf2;
}


.member-summary-text {
  font-size: 24rpx;
  font-weight: 700;
  color: #475467;
  line-height: 1.4;
}


.member-summary-card--member .member-summary-text { color: #1d4f91; }


.summary-mode-pill { height: 46rpx; padding: 0 18rpx; border-radius: 999rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; text { color: var(--text-inverse); font-size: 24rpx; font-weight: 900; } }


.summary-table-no { font-size: 32rpx; color: var(--text-1); font-weight: 900; line-height: 1; }


.summary-table-tip { color: #9a6f22; font-size: 24rpx; font-weight: 800; flex-shrink: 0; margin-left: auto; }


.confirm-card { background: var(--bg-card); border: 1rpx solid #eef1f3; border-radius: var(--radius-card); margin-bottom: 18rpx; overflow: hidden; }


.selected-items-summary { min-height: 118rpx; padding: 0 28rpx; display: flex; justify-content: space-between; align-items: center; gap: 18rpx; }


.selected-items-title-wrap { display: flex; flex-direction: column; gap: 8rpx; min-width: 0; }


.confirm-title-line { display: flex; align-items: center; gap: 10rpx; min-width: 0; }


.confirm-title-icon { flex-shrink: 0; color: var(--brand); font-size: 30rpx; line-height: 34rpx; }


.selected-items-title { color: var(--text-1); font-size: 34rpx; font-weight: 900; }


.selected-items-action { display: flex; align-items: center; gap: 18rpx; flex-shrink: 0; color: var(--text-2); }


.selected-items-amount { color: var(--brand); font-size: 34rpx; font-weight: 900; }


.selected-items-toggle-icon { color: var(--text-3); font-size: 28rpx; line-height: 32rpx; }


.cart-items-panel { border-top: 1rpx solid #edf0f2; padding: 0 0 8rpx; }


.cart-items { max-height: 34vh; padding: 0 28rpx; box-sizing: border-box; }


.cart-row { display: flex; align-items: center; gap: 16rpx; padding: 24rpx 0; border-bottom: 1rpx solid #edf0f2; }


.cart-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }


.cart-row-name { font-size: 31rpx; font-weight: 800; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.cart-row-spec { font-size: 22rpx; color: var(--text-3); }


.cart-row-right { display: flex; align-items: center; gap: 14rpx; flex-shrink: 0; }


.cart-row-price { min-width: 82rpx; text-align: right; font-size: 30rpx; font-weight: 900; color: var(--brand); }


.cart-clear-line {
  margin-top: 4rpx;
  padding: 18rpx 0 4rpx;
  border-top: 1rpx solid #f0f2f4;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  text { color: var(--text-3); font-size: 24rpx; font-weight: 700; }
  .iconfont { color: var(--text-3); font-size: 26rpx; line-height: 28rpx; }
}


.order-preference-section { padding: 26rpx 28rpx; }


.remark-summary-row { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; }


.remark-summary-action { display: flex; align-items: center; gap: 10rpx; min-width: 0; flex-shrink: 0; max-width: 60%; }


.remark-summary-text { color: var(--text-3); font-size: 26rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.remark-summary-toggle-icon { color: var(--text-3); font-size: 26rpx; line-height: 30rpx; flex-shrink: 0; }


.order-preference-section .remark-chips { margin-top: 22rpx; margin-bottom: 22rpx; }


.order-preference-section .remark-chip { margin-right: 14rpx; margin-bottom: 14rpx; padding: 14rpx 24rpx; border-radius: 999rpx; border: 1rpx solid #dfe5e8; background: var(--bg-card); }


.order-preference-section .remark-chip--on { border-color: var(--brand); background: #ecfbf3; }


.order-preference-section .remark-row { border-top: 1rpx solid #edf0f2; padding-top: 22rpx; }


.remark-label-wrap { display: flex; align-items: center; gap: 8rpx; flex-shrink: 0; }


.remark-label-icon { color: var(--brand); font-size: 28rpx; line-height: 32rpx; }


.price-summary-card { padding: 12rpx 28rpx 10rpx; }


.price-row { min-height: 88rpx; display: flex; align-items: center; justify-content: space-between; gap: 18rpx; color: #475467; font-size: 29rpx; border-bottom: 1rpx solid #edf0f2; }


.price-label-wrap { display: flex; align-items: center; gap: 10rpx; min-width: 0; }


.price-label-icon { flex-shrink: 0; color: var(--brand); font-size: 30rpx; line-height: 34rpx; }


.price-row:last-child { border-bottom: 0; }


.price-row--clickable { color: var(--text-1); }


.price-discount { color: var(--brand); font-weight: 800; }


.price-muted { color: var(--text-3); }


.price-row--payable { min-height: 110rpx; color: var(--text-1); font-size: 34rpx; font-weight: 900; }


.price-row--payable text:last-child { color: var(--brand); font-size: 52rpx; font-weight: 900; }


.checkout-btn-full {
  height: var(--btn-primary-height);
  border-radius: var(--btn-primary-radius);
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  box-shadow: 0 16rpx 32rpx rgba(16,196,105,0.22);
  text {
    color: var(--text-inverse);
    font-size: var(--btn-primary-font-size);
    font-weight: var(--btn-primary-font-weight);
  }
  .checkout-btn-icon {
    font-size: var(--btn-primary-font-size);
    line-height: 1.2;
    font-weight: 400;
  }
}


.checkout-btn-full--disabled { background: #cbd5e1; box-shadow: none; }



.remark-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  padding-bottom: 16rpx;
}



.remark-chip {
  padding: 8rpx 22rpx;
  border-radius: 32rpx;
  border: 1rpx solid #e5e7eb;
  background: #f8fafc;
  text { font-size: 24rpx; color: var(--text-3); }
}


.remark-chip--on {
  border-color: var(--brand);
  background: #f0fdf4;
  text { color: var(--brand); font-weight: 600; }
}



.remark-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 12rpx 0 16rpx;
  border-top: 1rpx solid var(--bg-muted);
}



.remark-label {
  flex-shrink: 0;
  font-size: 26rpx;
  color: var(--text-3);
}



.remark-input {
  flex: 1;
  font-size: 26rpx;
  color: var(--text-1);
  background: transparent;
}



.remark-placeholder { color: #c8c9cc; }




.cart-row-spec {
  display: block;
  font-size: 22rpx;
  color: var(--text-3);
  margin-top: 4rpx;
}



.order-remark-row { border-top: 0 !important; padding-top: 0 !important; }
</style>
