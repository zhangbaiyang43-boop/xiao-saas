<template>
  <view class="state-loading" :class="`state-loading--${size}`">
    <view class="state-loading-spinner"></view>
    <text class="state-loading-text">{{ text }}</text>
  </view>
</template>

<script>
export default {
  name: 'StateLoading',
  props: {
    text: { type: String, default: '正在加载' },
    // normal：整页/整卡片占用时的加载态；small：卡片内局部刷新时的轻量加载态
    size: { type: String, default: 'normal' }
  }
}
</script>

<style lang="scss" scoped>
.state-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.state-loading-spinner {
  width: 56rpx;
  height: 56rpx;
  margin-bottom: 20rpx;
  border: 6rpx solid var(--brand-light);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: state-loading-spin 0.9s linear infinite;
}

.state-loading-text {
  display: block;
  font-size: 30rpx;
  font-weight: 700;
  color: var(--text-1);
}

.state-loading--small {
  .state-loading-spinner {
    width: 44rpx;
    height: 44rpx;
    border-width: 4rpx;
    margin-bottom: 14rpx;
  }

  .state-loading-text {
    font-size: 26rpx;
    font-weight: 400;
    color: var(--text-3);
  }
}

@keyframes state-loading-spin {
  to { transform: rotate(360deg); }
}
</style>
