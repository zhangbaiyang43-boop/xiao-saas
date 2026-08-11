<template>
  <view class="state-error" :class="{ 'state-error--padded': padded }">
    <text class="state-error-title">{{ title }}</text>
    <text v-if="desc" class="state-error-desc">{{ desc }}</text>
    <button class="state-error-btn tap-shrink" @click="$emit('retry')">{{ retryText }}</button>
  </view>
</template>

<script>
// 错误态契约见知识库「客如云服务体系」：网络/加载失败必须用本组件；
// title 说清发生了什么，retryText 必须是可立即执行的下一步。
export default {
  name: 'StateError',
  props: {
    title: { type: String, default: '加载失败' },
    desc: { type: String, default: '' },
    retryText: { type: String, default: '重新加载' },
    padded: { type: Boolean, default: false },
  },
  emits: ['retry'],
}
</script>

<style lang="scss" scoped>
.state-error {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.state-error--padded {
  padding: 64rpx 40rpx;
  box-sizing: border-box;
}

.state-error-title {
  display: block;
  font-size: 30rpx;
  font-weight: 700;
  color: var(--text-1);
}

.state-error-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  color: var(--text-3);
  line-height: 1.6;
}

.state-error-btn {
  margin-top: 28rpx;
  width: 100%;
  max-width: 480rpx;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 24rpx;
  background: var(--brand);
  color: var(--text-inverse);
  font-size: 30rpx;
  font-weight: 600;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}
</style>
