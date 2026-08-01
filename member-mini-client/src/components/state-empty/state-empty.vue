<template>
  <view class="state-empty">
    <view class="state-empty-icon">
      <slot name="icon">{{ icon }}</slot>
    </view>
    <text class="state-empty-title">{{ title }}</text>
    <text v-if="desc" class="state-empty-desc">{{ desc }}</text>
    <button v-if="actionText" class="state-empty-btn tap-shrink" @click="$emit('action')">{{ actionText }}</button>
  </view>
</template>

<script>
export default {
  name: 'StateEmpty',
  props: {
    icon: { type: String, default: '🗂️' },
    title: { type: String, default: '暂无数据' },
    desc: { type: String, default: '' },
    actionText: { type: String, default: '' }
  },
  emits: ['action']
}
</script>

<style lang="scss" scoped>
.state-empty {
  text-align: center;
}

.state-empty-icon {
  font-size: 72rpx;
  line-height: 1;
}

.state-empty-title {
  display: block;
  margin-top: 16rpx;
  font-size: 30rpx;
  font-weight: 600;
  color: #333;
}

.state-empty-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  color: #9ca3af;
  line-height: 1.6;
}

.state-empty-btn {
  margin-top: 28rpx;
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 24rpx;
  background: #07C160;
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}
</style>
