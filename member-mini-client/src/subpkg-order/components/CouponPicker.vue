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
