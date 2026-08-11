<template>
  <view class="hero-stat">
    <template v-if="loading">
      <text class="hero-stat-value hero-stat-value--pending">--</text>
      <text class="hero-stat-label">{{ loadingLabel }}</text>
    </template>
    <template v-else-if="error">
      <text class="hero-stat-value hero-stat-value--pending">--</text>
      <text class="hero-stat-label hero-stat-label--error tap-shrink" @click="$emit('retry')">{{ errorLabel }}</text>
    </template>
    <template v-else>
      <text class="hero-stat-value">{{ value }}</text>
      <text class="hero-stat-label">{{ label }}</text>
    </template>
  </view>
</template>

<script>
// 顶部彩色 header 里的"大数字 + 说明文字"展示，points.vue（积分余额）使用。
export default {
  name: 'StateHeroStat',
  props: {
    loading: { type: Boolean, default: false },
    error: { type: Boolean, default: false },
    value: { type: [String, Number], default: '' },
    label: { type: String, default: '' },
    loadingLabel: { type: String, default: '正在加载…' },
    errorLabel: { type: String, default: '加载失败，点击重试' }
  },
  emits: ['retry']
}
</script>

<style lang="scss" scoped>
.hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.hero-stat-value {
  font-size: 72rpx;
  font-weight: 900;
  color: var(--text-inverse);
  line-height: 1;
}

.hero-stat-value--pending {
  opacity: 0.6;
}

.hero-stat-label {
  margin-top: 12rpx;
  font-size: 26rpx;
  color: rgba(255, 255, 255, 0.8);
}

.hero-stat-label--error {
  text-decoration: underline;
  color: var(--text-inverse);
}
</style>
