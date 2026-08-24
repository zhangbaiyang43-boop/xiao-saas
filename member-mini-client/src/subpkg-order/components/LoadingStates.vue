<template>
  <view v-if="loadError && !loading" class="loading-mask">
    <view class="loading-error">
      <state-error
        title="菜单加载失败"
        retry-text="重新加载"
        @retry="$emit('retry-load')"
      />
    </view>
  </view>

  <view v-if="loading" class="loading-mask skeleton-mask">
    <view class="skeleton-nav">
      <view v-for="n in 6" :key="n" class="skeleton-nav-item"></view>
    </view>
    <view class="skeleton-list">
      <view v-for="n in 4" :key="n" class="skeleton-dish">
        <view class="skeleton-thumb"></view>
        <view class="skeleton-lines">
          <view class="skeleton-line skeleton-line--title"></view>
          <view class="skeleton-line skeleton-line--desc"></view>
          <view class="skeleton-line skeleton-line--price"></view>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import StateError from '@/components/state-error/state-error.vue'

// 从 menu.vue 拆出来的两个加载态遮罩：加载失败提示（loadError）和骨架屏
// （loading）。失败态走已有 StateError；骨架屏仍是 Constitution 允许的独立 primitive。
export default {
  name: 'LoadingStates',
  components: { StateError },
  props: {
    loadError: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
  },
  emits: ['retry-load'],
}
</script>

<style lang="scss">
.loading-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(255,255,255,0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24rpx;
}



.loading-error {
  width: 100%;
  padding: 0 64rpx;
  box-sizing: border-box;
}



.skeleton-mask {
  position: fixed;
  top: calc(176rpx + env(safe-area-inset-top));
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  justify-content: flex-start;
  gap: 0;
}



.skeleton-nav {
  width: 156rpx;
  flex: 0 0 156rpx;
  background: #F6F7F8;
  padding-top: 20rpx;
  box-sizing: border-box;
}



.skeleton-nav-item {
  height: 36rpx;
  margin: 0 28rpx 32rpx;
  border-radius: 8rpx;
}



.skeleton-list {
  flex: 1;
  min-width: 0;
  padding: 20rpx 20rpx 0;
  box-sizing: border-box;
  overflow: hidden;
}



.skeleton-dish {
  display: flex;
  align-items: flex-start;
  height: 192rpx;
  margin-bottom: 24rpx;
}



.skeleton-thumb {
  width: 192rpx;
  height: 192rpx;
  border-radius: 20rpx;
  flex-shrink: 0;
}



.skeleton-lines {
  flex: 1;
  min-width: 0;
  margin-left: 20rpx;
  padding-top: 10rpx;
  display: flex;
  flex-direction: column;
  gap: 18rpx;
}



.skeleton-line {
  height: 26rpx;
  border-radius: 8rpx;
}



.skeleton-line--title { width: 55%; height: 32rpx; }


.skeleton-line--desc { width: 85%; }


.skeleton-line--price { width: 28%; height: 34rpx; margin-top: 36rpx; }



.skeleton-nav-item,
.skeleton-thumb,
.skeleton-line {
  background: linear-gradient(90deg, #edeff1 25%, #f7f8f9 37%, #edeff1 63%);
  background-size: 400% 100%;
  animation: skeletonShimmer 1.4s ease infinite;
}



@keyframes skeletonShimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}
</style>
