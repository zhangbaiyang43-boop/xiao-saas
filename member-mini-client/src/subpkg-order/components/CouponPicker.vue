<template>
  <base-sheet
    layer="blocking-top"
    title="优惠券"
    @close="$emit('cancel')"
  >
      <view v-if="summaryText" class="cp-summary-wrap">
        <text class="cp-summary">{{ summaryText }}</text>
      </view>
      <view class="cp-summary-wrap">
        <text class="cp-note">券每次最多抵订单金额的 20%，上方金额已按本单计算</text>
      </view>
      <scroll-view class="cp-list" scroll-y>
        <view
          v-if="bestCoupon"
          class="cp-option cp-option--best"
          :class="{ 'cp-option--on': selectedCouponId === bestCoupon.id }"
          @click="$emit('select-coupon', bestCoupon)"
        >
          <view class="cp-best-badge"><text>最划算</text></view>
          <view class="cp-option-amount"><text>¥{{ couponPickerAmount(bestCoupon) }}</text></view>
          <view class="cp-option-main">
            <text class="cp-option-name">{{ bestCoupon.name || '优惠券' }}</text>
            <text class="cp-option-cond">{{ couponPickerCondText(bestCoupon) }}</text>
          </view>
          <text :class="['cp-radio-icon', 'iconfont', selectedCouponId === bestCoupon.id ? 'icon-roundcheckfill' : 'icon-roundcheck']"></text>
        </view>

        <view
          v-for="c in otherEligibleCoupons"
          :key="c.id"
          class="cp-option"
          :class="{ 'cp-option--on': selectedCouponId === c.id }"
          @click="$emit('select-coupon', c)"
        >
          <view class="cp-option-amount"><text>¥{{ couponPickerAmount(c) }}</text></view>
          <view class="cp-option-main">
            <text class="cp-option-name">{{ c.name || '优惠券' }}</text>
            <text class="cp-option-cond">{{ couponPickerCondText(c) }}</text>
          </view>
          <text :class="['cp-radio-icon', 'iconfont', selectedCouponId === c.id ? 'icon-roundcheckfill' : 'icon-roundcheck']"></text>
        </view>

        <view v-if="ineligibleCoupons.length" class="cp-section">
          <text class="cp-section-title">还差一点点</text>
          <view
            v-for="c in ineligibleCoupons"
            :key="c.id"
            class="cp-option cp-option--disabled"
            @click="$emit('select-coupon', c)"
          >
            <view class="cp-option-amount"><text>¥{{ couponPickerAmount(c) }}</text></view>
            <view class="cp-option-main">
              <text class="cp-option-name">{{ c.name || '优惠券' }}</text>
              <text class="cp-option-cond">还差{{ formatPrice(Math.max(0, Number(c.min_amount || c.threshold_amount || 0) - totalPrice)) }}元可用</text>
            </view>
          </view>
        </view>

        <view v-if="!couponPickerList.length" class="cp-empty"><text>暂无可用优惠券</text></view>

        <view class="cp-skip-wrap">
          <text class="cp-skip-link" @click="$emit('select-coupon', null)">不使用优惠券</text>
        </view>
      </scroll-view>
  </base-sheet>
</template>

<script>
import BaseSheet from '@/components/base-sheet/base-sheet.vue'

// 从 menu.vue 拆出来的优惠券选择弹层（原来是 showCouponPicker 那一段模板）。
// 纯展示组件，不带任何业务逻辑——点击关闭/选券都只 emit 出去，真正的处理函数
// 还是原来 menu.vue 里的 closeCouponPicker/pickCoupon，一行都没有改。可用性
// 判断（c.eligible）、金额和条件文案的计算，全部留在父组件，这里只读取父组件
// 算好的结果。
// 外壳已从 legacy .mask 迁到 BaseSheet blocking-top：叠在结算确认之上时必须
// 高于 CheckoutSheet 的 blocking（3200 > 3100），不能再靠 DOM 顺序。
export default {
  name: 'CouponPicker',
  components: { BaseSheet },
  props: {
    selectedCouponId: { type: [Number, String], default: null },
    couponPickerList: { type: Array, default: () => [] },
    totalPrice: { type: Number, default: 0 },
    couponPickerAmount: { type: Function, required: true },
    couponPickerCondText: { type: Function, required: true },
    formatPrice: { type: Function, required: true },
  },
  emits: ['cancel', 'select-coupon'],
  computed: {
    eligibleCoupons() {
      return this.couponPickerList.filter(c => c.eligible)
    },
    bestCoupon() {
      return this.eligibleCoupons[0] || null
    },
    otherEligibleCoupons() {
      return this.eligibleCoupons.slice(1)
    },
    ineligibleCoupons() {
      return this.couponPickerList.filter(c => !c.eligible)
    },
    selectedCouponItem() {
      if (!this.selectedCouponId) return null
      return this.couponPickerList.find(c => c.id === this.selectedCouponId) || null
    },
    summaryText() {
      if (!this.selectedCouponItem) return ''
      return `已为您自动选用最划算的一张，已减¥${this.couponPickerAmount(this.selectedCouponItem)}`
    },
  },
}
</script>

<style lang="scss">
.cp-summary-wrap {
  flex-shrink: 0;
  padding: 0 36rpx 12rpx;
}

.cp-summary {
  display: block;
  font-size: 24rpx;
  color: var(--text-3);
  line-height: 1.4;
}

.cp-note {
  display: block;
  font-size: 22rpx;
  color: var(--text-4, var(--text-3));
  line-height: 1.4;
}



.cp-list {
  flex: 1;
  min-height: 0;
  padding: 0 24rpx 24rpx;
  box-sizing: border-box;
}



.cp-option {
  position: relative;
  display: flex;
  align-items: center;
  gap: 20rpx;
  padding: 22rpx 20rpx;
  margin-bottom: 16rpx;
  border-radius: 20rpx;
  border: 2rpx solid #edf0f2;
  background: #fafbfc;
  box-sizing: border-box;
}



.cp-option--best {
  border-width: 3rpx;
  border-color: var(--brand);
  background: #ecfbf3;
  padding-top: 36rpx;
}



.cp-option--on {
  border-color: var(--brand);
  background: #ecfbf3;
}



.cp-option--disabled {
  opacity: .5;
}



.cp-best-badge {
  position: absolute;
  top: 12rpx;
  left: 20rpx;
  height: 36rpx;
  padding: 0 14rpx;
  border-radius: 999rpx;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  text { color: #fff; font-size: 20rpx; font-weight: 900; }
}



.cp-option-amount {
  flex-shrink: 0;
  min-width: 108rpx;
  text-align: center;
  /* 券面额用红金色而不是品牌绿，跟"选中态"用色分开：绿色始终代表"这个选项被选中"，
     红金色代表"这是一张券"，两套含义混用同一个颜色会互相干扰。 */
  text { color: #ff3018; font-size: 40rpx; font-weight: 900; }
}



.cp-option-main {
  flex: 1;
  min-width: 0;
}



.cp-option-name {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: var(--text-1);
}



.cp-option-cond {
  display: block;
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--text-3);
}



.cp-radio-icon {
  flex-shrink: 0;
  width: 44rpx;
  height: 44rpx;
  color: #d7dce2;
  font-size: 42rpx;
  line-height: 44rpx;
  text-align: center;
}



.cp-option--on .cp-radio-icon {
  color: var(--brand);
}



.cp-section {
  margin-top: 8rpx;
  padding-top: 8rpx;
}



.cp-section-title {
  display: block;
  margin: 0 4rpx 12rpx;
  font-size: 22rpx;
  color: var(--text-3);
  font-weight: 700;
}



.cp-empty {
  padding: 64rpx 0 24rpx;
  text-align: center;
  text { color: var(--text-3); font-size: 26rpx; }
}



.cp-skip-wrap {
  padding: 12rpx 0 8rpx;
  text-align: center;
}



.cp-skip-link {
  display: inline-block;
  padding: 16rpx 8rpx;
  font-size: 26rpx;
  color: var(--text-3);
  text-decoration: underline;
}
</style>
