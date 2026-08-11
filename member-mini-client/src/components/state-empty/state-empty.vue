<template>
  <view class="state-empty" :class="{ 'state-empty--padded': padded }">
    <view class="state-empty-icon">
      <slot name="icon">{{ icon }}</slot>
    </view>
    <text class="state-empty-title">{{ title }}</text>
    <text v-if="desc" class="state-empty-desc">{{ desc }}</text>
    <button v-if="actionText" class="state-empty-btn tap-shrink" @click="$emit('action')">{{ actionText }}</button>
  </view>
</template>

<script>
// 空态契约见知识库「客如云服务体系」：没有数据但不是错误时用本组件，
// 不要复用 StateError（否则会误导用户去重试一个不会变化的空状态）。
export default {
  name: 'StateEmpty',
  props: {
    icon: { type: String, default: '🗂️' },
    title: { type: String, default: '暂无数据' },
    desc: { type: String, default: '' },
    actionText: { type: String, default: '' },
    // 弹层/窄容器里加内边距，避免贴边
    padded: { type: Boolean, default: false },
  },
  emits: ['action'],
}
</script>

<style lang="scss" scoped>
.state-empty {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.state-empty--padded {
  padding: 64rpx 40rpx;
  box-sizing: border-box;
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
  color: var(--text-1);
}

.state-empty-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  color: var(--text-3);
  line-height: 1.6;
}

.state-empty-btn {
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
