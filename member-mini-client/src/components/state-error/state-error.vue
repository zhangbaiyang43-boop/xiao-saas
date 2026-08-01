<template>
  <view class="state-error">
    <text class="state-error-title">{{ title }}</text>
    <text v-if="desc" class="state-error-desc">{{ desc }}</text>
    <button class="state-error-btn tap-shrink" @click="$emit('retry')">{{ retryText }}</button>
  </view>
</template>

<script>
export default {
  name: 'StateError',
  props: {
    title: { type: String, default: '加载失败' },
    desc: { type: String, default: '' },
    retryText: { type: String, default: '重新加载' }
  },
  emits: ['retry']
}
</script>

<style lang="scss" scoped>
.state-error {
  text-align: center;
}

.state-error-title {
  display: block;
  font-size: 30rpx;
  font-weight: 700;
  color: #111827;
}

.state-error-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  color: #6b7280;
}

.state-error-btn {
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
