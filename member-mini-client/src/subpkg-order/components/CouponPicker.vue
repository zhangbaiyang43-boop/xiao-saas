<template>
  <view class="mask" @click="$emit('cancel')">
    <view class="coupon-picker-sheet" @click.stop>
      <view class="cp-head">
        <text class="cp-title">选择优惠券</text>
        <text class="cp-close iconfont icon-close" @click="$emit('cancel')"></text>
      </view>
      <scroll-view class="cp-list" scroll-y>
        <view class="cp-option" :class="{ 'cp-option--on': !selectedCouponId }" @click="$emit('select-coupon', null)">
          <view class="cp-option-main">
            <text class="cp-option-name">不使用优惠券</text>
          </view>
          <text :class="['cp-radio-icon', 'iconfont', !selectedCouponId ? 'icon-roundcheckfill' : 'icon-roundcheck']"></text>
        </view>
        <view
          v-for="c in couponPickerList"
          :key="c.id"
          class="cp-option"
          :class="{ 'cp-option--on': selectedCouponId === c.id, 'cp-option--disabled': !c.eligible }"
          @click="$emit('select-coupon', c)"
        >
          <view class="cp-option-amount"><text>¥{{ couponPickerAmount(c) }}</text></view>
          <view class="cp-option-main">
            <text class="cp-option-name">{{ c.name || '优惠券' }}</text>
            <text class="cp-option-cond">{{ c.eligible ? couponPickerCondText(c) : '还差' + formatPrice(Math.max(0, Number(c.min_amount || c.threshold_amount || 0) - totalPrice)) + '元可用' }}</text>
          </view>
          <text :class="['cp-radio-icon', 'iconfont', selectedCouponId === c.id ? 'icon-roundcheckfill' : 'icon-roundcheck']"></text>
        </view>
        <view v-if="!couponPickerList.length" class="cp-empty"><text>暂无可用优惠券</text></view>
      </scroll-view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的优惠券选择弹层（原来是 showCouponPicker 那一段模板）。
// 纯展示组件，不带任何业务逻辑——点击关闭/选券都只 emit 出去，真正的处理函数
// 还是原来 menu.vue 里的 closeCouponPicker/pickCoupon，一行都没有改。可用性
// 判断（c.eligible）、金额和条件文案的计算，全部留在父组件，这里只读取父组件
// 算好的结果。
export default {
  name: 'CouponPicker',
  props: {
    selectedCouponId: { type: [Number, String], default: null },
    couponPickerList: { type: Array, default: () => [] },
    totalPrice: { type: Number, default: 0 },
    couponPickerAmount: { type: Function, required: true },
    couponPickerCondText: { type: Function, required: true },
    formatPrice: { type: Function, required: true },
  },
  emits: ['cancel', 'select-coupon'],
}
</script>

<style lang="scss">
.coupon-picker-sheet {
  width: 100%;
  max-height: 76vh;
  background: #fff;
  border-radius: 32rpx 32rpx 0 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  animation: slide-up 0.25s ease;
}



.cp-head {
  position: relative;
  flex-shrink: 0;
  padding: 28rpx 32rpx 18rpx;
  text-align: center;
}



.cp-title {
  font-size: 32rpx;
  font-weight: 900;
  color: var(--text-1);
}



.cp-close {
  position: absolute;
  right: 20rpx;
  top: 16rpx;
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 34rpx;
  line-height: 64rpx;
  text-align: center;
}



.cp-list {
  flex: 1;
  min-height: 0;
  padding: 0 24rpx calc(24rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}



.cp-option {
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



.cp-option--on {
  border-color: var(--brand);
  background: #ecfbf3;
}



.cp-option--disabled {
  opacity: .5;
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



.cp-empty {
  padding: 64rpx 0;
  text-align: center;
  text { color: var(--text-3); font-size: 26rpx; }
}
</style>
