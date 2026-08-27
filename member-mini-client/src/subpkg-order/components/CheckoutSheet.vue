<template>
  <base-sheet
    class="order-confirm-sheet"
    layer="blocking"
    :title="confirmationText.title"
    @close="$emit('close')"
  >
      <scroll-view class="order-confirm-content" scroll-y>
        <!-- 确认订单和看订单共用同一张 `.to-*` 点单卡，让顾客两头看到的是同一个东西。
             这里额外的只有"可编辑"（步进器 + 选中圈）和桌牌下面那行堂食/会员信息。 -->
        <view class="to-card" :class="{ 'checkout-card--missing': !tableNo }">
          <view class="to-plate" @click="$emit('show-table-hint')">
            <text class="to-plate-table">{{ tableNo || orderModeText.unknownTable }}</text>
            <text class="to-plate-unit">桌</text>
          </view>
          <view class="checkout-plate-meta">
            <text class="checkout-mode-text">{{ orderModeText.dineIn }}</text>
            <text v-if="memberSummaryText" class="checkout-meta-sep">·</text>
            <text v-if="memberSummaryText" class="checkout-member-text">{{ memberSummaryText }}</text>
          </view>
          <text v-if="!tableNo" class="checkout-plate-tip">{{ confirmationText.tableMissing }}</text>

          <view class="to-divider"></view>

          <view class="checkout-items-head" @click="$emit('toggle-items-expanded')">
            <view class="checkout-items-title-wrap">
              <text class="checkout-items-icon iconfont icon-list"></text>
              <text class="checkout-items-title">{{ confirmationText.selectedItems }} · 共{{ totalCount }}份</text>
            </view>
            <view class="checkout-items-head-action">
              <text class="checkout-items-amount">{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text>
              <text :class="['checkout-items-toggle', 'iconfont', itemsExpanded ? 'icon-pullup' : 'icon-unfold']"></text>
            </view>
          </view>

          <view v-if="itemsExpanded" class="to-list">
            <view v-for="item in cartItems" :key="item.specKey || item.id" class="to-drow">
              <view class="checkout-item-selected"><text>✓</text></view>
              <image
                v-if="item.image_url || item.image || item.cover_image"
                class="to-drow-img"
                :src="item.image_url || item.image || item.cover_image"
                mode="aspectFill"
              />
              <view v-else class="to-drow-img to-drow-img--ph">
                <image class="to-drow-img-ph" src="/static/order/dish-placeholder.png" mode="aspectFit" />
              </view>
              <view class="to-drow-main">
                <text class="to-drow-name">{{ item.name }}</text>
                <text v-if="item.specLabel" class="to-drow-spec">{{ item.specLabel }}</text>
                <text v-else class="to-drow-spec">{{ confirmationText.currency }}{{ Number(item.price || 0).toFixed(2) }}/份</text>
              </view>
              <view class="checkout-item-side">
                <view class="checkout-item-counter">
                  <view class="counter-btn minus sm" @click="$emit('remove-from-cart', item)"><text class="iconfont icon-move"></text></view>
                  <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === (item.specKey || item.id) }">{{ item.qty }}</text>
                  <view class="counter-btn plus sm" @click="$emit('increase-cart-item', item)"><text class="iconfont icon-add"></text></view>
                </view>
                <text class="checkout-item-subtotal">小计 {{ confirmationText.currency }}{{ (item.price * item.qty).toFixed(2) }}</text>
              </view>
            </view>
            <view class="checkout-clear-line" @click="$emit('clear-cart')">
              <text class="iconfont icon-delete"></text>
              <text>{{ confirmationText.clear }}</text>
            </view>
          </view>

          <view class="to-line to-line--sub">
            <text class="to-line-l">{{ confirmationText.goodsAmount }}</text>
            <text class="to-line-v">{{ confirmationText.currency }}{{ totalPrice.toFixed(2) }}</text>
          </view>
          <!-- 优惠券只在这里出现一次：既是明细里的减项（在应付金额旁边一眼可见），
               也是换券入口（点开选券）。不在下面「订单详情」里再放一条。 -->
          <view
            class="to-line checkout-coupon-line"
            :class="{ 'to-line--sub': discountAmount <= 0 }"
            @click="$emit('open-coupon-picker')"
          >
            <text class="to-line-l">{{ confirmationText.coupon }}</text>
            <text v-if="discountAmount > 0" class="to-line-v">-{{ confirmationText.currency }}{{ discountAmount.toFixed(2) }} {{ confirmationText.arrow }}</text>
            <text v-else-if="availableCoupons.length > 0" class="to-line-v">{{ availableCoupons.length }}{{ confirmationText.couponAvailable }} {{ confirmationText.arrow }}</text>
            <text v-else class="to-line-v">{{ confirmationText.couponNone }} {{ confirmationText.arrow }}</text>
          </view>
          <view class="to-foot">
            <text class="to-foot-l">共 {{ totalCount }} 份 · {{ confirmationText.payable }}</text>
            <text class="to-foot-v"><text class="to-cur">{{ confirmationText.currency }}</text>{{ wechatPayAmount.toFixed(2) }}</text>
          </view>
        </view>

        <view class="to-detail">
          <view class="to-detail-head" @click="$emit('toggle-order-remark-expanded')">
            <text class="to-detail-t">订单详情</text>
            <text class="to-detail-a">{{ orderRemarkExpanded ? '收起' : '展开' }}</text>
          </view>

          <view v-if="orderRemarkExpanded" class="to-detail-body">
            <view class="checkout-detail-section">
              <view class="checkout-detail-row">
                <view class="checkout-detail-label"><text class="iconfont icon-edit"></text><text>{{ confirmationText.orderRemark }}</text></view>
                <text class="checkout-detail-value">{{ orderRemarkSummary }}</text>
              </view>
              <view v-if="orderRemarkChips.length" class="remark-chips">
                <view
                  v-for="chip in orderRemarkChips"
                  :key="chip"
                  class="remark-chip"
                  :class="{ 'remark-chip--on': remark.includes(chip) }"
                  @click="$emit('toggle-remark-chip', chip)"
                ><text>{{ chip }}</text></view>
              </view>
              <view class="remark-row order-remark-row">
                <text v-if="!showOrderRemarkExtra" class="item-remark-extra-toggle" @click="$emit('show-order-remark-extra')">+ 其他要求</text>
                <input v-else class="remark-input" v-model="remarkModel" :placeholder="confirmationText.orderRemarkPlaceholder" placeholder-class="remark-placeholder" maxlength="60" />
              </view>
            </view>

            <view class="checkout-detail-row">
              <view class="checkout-detail-label"><text class="iconfont icon-pay"></text><text>支付方式</text></view>
              <text class="checkout-detail-value">{{ confirmPaymentLabel }}</text>
            </view>
          </view>
        </view>
      </scroll-view>

      <template #footer>
        <view class="order-confirm-bottom">
          <view class="checkout-btn-full" :class="{ 'checkout-btn-full--disabled': !canSubmitOrder || ordering || paying }" @click="$emit('checkout')">
            <text class="checkout-btn-icon iconfont icon-pay"></text><text>{{ payButtonText }}</text>
          </view>
        </view>
      </template>
  </base-sheet>
</template>

<script>
import BaseSheet from '@/components/base-sheet/base-sheet.vue'

// 从 menu.vue 拆出来的购物车/结算确认弹层（原来是 showCart 那一段模板）。纯展
// 示组件，不带任何业务逻辑——所有需要改父组件状态的动作（关闭、桌台提示、展开
// /收起已选菜品、加减数量、清空购物车、备注展开/切换/输入、打开优惠券选择器、
// 提交结算）都只 emit 出去，真正的处理函数还是原来 menu.vue 里那几个，一行都没改。
//
// 视觉：卡片骨架复用 `./table-order-card.scss` 的 `.to-*`，跟"本桌订单"两个弹层
// 是同一张点单卡。这里只保留确认页专属的东西：可编辑控件（选中圈 + 步进器 +
// 小计）、桌牌下面那行堂食/会员信息、单个提交 CTA、备注区。
export default {
  name: 'CheckoutSheet',
  components: { BaseSheet },
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
@import './table-order-card.scss';

/* 底色跟"本桌订单"的 .table-order-sheet 一致——卡片浮在浅灰上，边框才有对比。 */
.order-confirm-sheet { background: var(--bg-subtle); }

/* mp-weixin 里把 flex 子元素当 <scroll-view> 用，必须 flex:1 + min-height:0 + height:0
   三个一起写——只写 flex:1 它会按内容撑高（订单详情展开后内容超过 86vh 时，
   滚动区不滚、直接把 #footer 的提交按钮顶到屏幕外）。 */
.order-confirm-content {
  flex: 1;
  min-height: 0;
  height: 0;
  padding: 8rpx 24rpx 20rpx;
  box-sizing: border-box;
}

.order-confirm-bottom {
  flex-shrink: 0;
  /* 真机的底部安全区由 BaseSheet 的 .base-sheet-surface padding-bottom 兜；
     这里再垫 12rpx 最小底距，避免开发者工具里 env()=0 时按钮完全贴边。 */
  padding: 16rpx 24rpx 12rpx;
  border-top: 1rpx solid #edf0f2;
  background: rgba(255, 255, 255, 0.98);
}

/* 未识别桌号：暖色警示（不是错误红），提示顾客先确认桌号 */
.checkout-card--missing {
  border-color: #fed7aa;
  background: #fffdf9;
}

/* 桌牌下方那行：堂食 · 会员权益。确认页专属信息，居中、品牌色。 */
.checkout-plate-meta {
  max-width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  margin-top: 8rpx;
  color: var(--brand);
  font-size: 23rpx;
  font-weight: 700;
}

.checkout-mode-text { flex-shrink: 0; }
.checkout-meta-sep { color: #b7c2bc; }

.checkout-member-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.checkout-plate-tip {
  display: block;
  margin-top: 6rpx;
  text-align: center;
  color: #a06516;
  font-size: 22rpx;
  font-weight: 700;
}

/* 已选商品可折叠头（确认页专属——看订单时清单是常显的） */
.checkout-items-head {
  min-height: 82rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
}

.checkout-items-title-wrap,
.checkout-items-head-action {
  min-width: 0;
  display: flex;
  align-items: center;
}

.checkout-items-title-wrap { gap: 10rpx; }
.checkout-items-head-action { flex-shrink: 0; gap: 12rpx; }
.checkout-items-icon { color: var(--brand); font-size: 26rpx; }
.checkout-items-title { color: var(--text-1); font-size: 26rpx; font-weight: 700; }
.checkout-items-amount { color: var(--brand); font-size: 26rpx; font-weight: 800; }
.checkout-items-toggle { color: var(--text-3); font-size: 23rpx; }

/* 菜品行左侧的选中圈——确认页专属，占看订单页四点进度的那个位置 */
.checkout-item-selected {
  width: 32rpx;
  height: 32rpx;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;

  text { color: var(--text-inverse); font-size: 20rpx; font-weight: 900; }
}

/* 行右侧：步进器 + 小计（确认页专属，看订单时是只读的 ×N ¥X） */
.checkout-item-side {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6rpx;
}

.checkout-item-counter { display: flex; align-items: center; gap: 10rpx; }

.checkout-item-subtotal {
  color: var(--text-3);
  font-size: 19rpx;
  font-variant-numeric: tabular-nums;
}

.checkout-clear-line {
  min-height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  color: var(--text-3);

  text { font-size: 22rpx; font-weight: 700; }
  .iconfont { font-size: 24rpx; }
}

/* 订单详情折叠区里的行（备注 / 优惠券 / 支付方式）——确认页专属内容 */
.checkout-detail-section,
.checkout-detail-row { border-top: 1rpx solid #edf0f2; }

.checkout-detail-row {
  min-height: 86rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18rpx;
  color: var(--text-2);
  font-size: 25rpx;
}

.checkout-detail-label {
  flex-shrink: 0;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10rpx;

  .iconfont { color: var(--brand); font-size: 27rpx; }
}

.checkout-detail-value {
  min-width: 0;
  overflow: hidden;
  color: var(--text-3);
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 优惠券行——明细里的减项 + 换券入口合一，避免"优惠券"在卡片和详情里各显示一次。
   有券时走 .to-line-v 的减项红；没券/可选时套 .to-line--sub 收敛成中性灰。 */
.checkout-coupon-line .to-line-v { font-variant-numeric: tabular-nums; }
.checkout-coupon-line:active { opacity: .6; }

.checkout-detail-section .remark-chips { margin-top: 2rpx; }

.remark-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  padding-bottom: 12rpx;
}

.remark-chip {
  padding: 10rpx 20rpx;
  border: 1rpx solid #e2e6e8;
  border-radius: 28rpx;
  background: #f8faf9;

  text { color: var(--text-3); font-size: 22rpx; }
}

.remark-chip--on {
  border-color: var(--brand);
  background: #ecfbf3;

  text { color: var(--brand); font-weight: 700; }
}

.remark-row {
  display: flex;
  align-items: center;
  min-height: 62rpx;
  padding-bottom: 12rpx;
}

.remark-input {
  flex: 1;
  min-width: 0;
  color: var(--text-1);
  font-size: 24rpx;
  background: transparent;
}

.remark-placeholder { color: #b2b8bf; }
.order-remark-row { border-top: 0; padding-top: 0; }

/* 提交 CTA——尺寸对齐"本桌订单"的 .table-account-action--primary
   （92rpx 高 / 46rpx 胶囊 / 29rpx 字 / 无阴影），只是这里是单按钮带支付图标。 */
.checkout-btn-full {
  height: 92rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10rpx;
  border-radius: 46rpx;
  background: var(--brand);

  text { color: var(--text-inverse); font-size: 29rpx; font-weight: 900; }
  .checkout-btn-icon { font-size: 30rpx; line-height: 1; font-weight: 400; }
}

.checkout-btn-full--disabled { background: #cbd5e1; }
</style>
