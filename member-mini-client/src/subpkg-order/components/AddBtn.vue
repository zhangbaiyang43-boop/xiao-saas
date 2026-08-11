<template>
  <view
    class="add-btn"
    :class="[`add-btn--${size}`, { 'add-btn--pressing': pressing }]"
    @click.stop="$emit('click')"
  >
    <text class="add-btn-icon iconfont icon-add"></text>
  </view>
</template>

<script>
// 全站「绿底圆形加号」唯一组件。减号仍用 _shared.scss 的 .counter-btn.minus。
// 调用方务必显式传 size（md/sm），避免 uni-app 在仅有 pressing:false 时把 props 收成空。
export default {
  name: 'AddBtn',
  props: {
    size: { type: String, default: 'md' }, // sm | md
    // 用 Number 0/1 也行；布尔 false 单独作为唯一动态 prop 时 mp 编译易踩坑
    pressing: { type: Boolean, default: false },
  },
  emits: ['click'],
}
</script>

<style lang="scss">
.add-btn {
  border-radius: 50%;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-sizing: border-box;
  transform-origin: center;
  transition: transform 160ms ease-out;
}

.add-btn-icon {
  color: var(--text-inverse);
  font-weight: 400;
  line-height: 1;
}

.add-btn--md {
  width: 72rpx;
  height: 72rpx;
}
.add-btn--md .add-btn-icon { font-size: 30rpx; }

.add-btn--sm {
  width: 52rpx;
  height: 52rpx;
}
.add-btn--sm .add-btn-icon { font-size: 26rpx; }

.add-btn--pressing,
.add-btn:active {
  transform: scale(0.92);
}
</style>
