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
                  <view class="counter-btn plus sm" @click="$emit('increase-cart-item', item)"><text class="iconfont icon-add"></text></view>
                  <text class="cart-row-price">{{ confirmationText.currency }}{{ formatPrice(item.price * item.qty) }}</text>
                </view>
              </view>
            </scroll-view>
            <view class="cart-clear-line" @click="$emit('clear-cart')"><text class="iconfont icon-delete"></text><text>{{ confirmationText.clear }}</text></view>
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
export default {
  name: 'CheckoutSheet',
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
    canSubmitOrder: { type: Boolean, default: false },
    ordering: { type: Boolean, default: false },
    paying: { type: Boolean, default: false },
    payButtonText: { type: String, default: '' },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    formatPrice: { type: Function, required: true },
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
