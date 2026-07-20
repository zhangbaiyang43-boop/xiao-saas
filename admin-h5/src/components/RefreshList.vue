<template>
  <div class="refresh-list" ref="listRef">
    <div 
      class="refresh-header" 
      :style="{ transform: `translateY(${pullDistance}px)` }"
      @touchstart="handleTouchStart"
      @touchmove="handleTouchMove"
      @touchend="handleTouchEnd"
    >
      <div class="refresh-indicator" v-if="isRefreshing">
        <van-loading type="spinner" color="#9356DC" />
        <span>刷新中...</span>
      </div>
      <div class="refresh-indicator" v-else-if="pullDistance > 60">
        <van-icon name="arrow-down" :style="{ transform: 'rotate(180deg)' }" />
        <span>松开刷新</span>
      </div>
      <div class="refresh-indicator" v-else-if="pullDistance > 10">
        <van-icon name="arrow-down" />
        <span>下拉刷新</span>
      </div>
    </div>
    
    <slot></slot>
    
    <div v-if="loading" class="loading-more">
      <van-loading type="spinner" color="#9356DC" />
      <span>加载中...</span>
    </div>
    
    <div v-else-if="!loading && hasMore" class="load-more-tip" @click="loadMore">
      <span>点击加载更多</span>
    </div>
    
    <div v-else-if="!hasMore && items.length > 0" class="no-more">
      <span>已加载全部</span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Icon as VanIcon, Loading as VanLoading } from 'vant'

defineProps({
  items: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  hasMore: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['refresh', 'loadMore'])

const listRef = ref(null)
const pullDistance = ref(0)
const isRefreshing = ref(false)
const startY = ref(0)
const isTouching = ref(false)

const handleTouchStart = (e) => {
  if (window.scrollY === 0) {
    startY.value = e.touches[0].clientY
    isTouching.value = true
  }
}

const handleTouchMove = (e) => {
  if (!isTouching.value) return
  
  const currentY = e.touches[0].clientY
  const diff = currentY - startY.value
  
  if (diff > 0 && window.scrollY === 0) {
    pullDistance.value = Math.min(diff * 0.5, 100)
    e.preventDefault()
  }
}

const handleTouchEnd = () => {
  if (!isTouching.value) return
  isTouching.value = false
  
  if (pullDistance.value > 60 && !isRefreshing.value) {
    isRefreshing.value = true
    emit('refresh')
    
    setTimeout(() => {
      pullDistance.value = 0
      isRefreshing.value = false
    }, 1500)
  } else {
    pullDistance.value = 0
  }
}

const loadMore = () => {
  emit('loadMore')
}
</script>

<style lang="scss" scoped>
.refresh-list {
  position: relative;
  min-height: 200px;
}

.refresh-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  display: flex;
  justify-content: center;
  align-items: center;
  transform-origin: top center;
  z-index: 10;
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  font-size: $font-size-xs;
  color: $text-tertiary;
  opacity: 1;
  transition: opacity 0.3s;
  
  .van-icon {
    font-size: 16px;
    transition: transform 0.3s;
  }
}

.loading-more,
.load-more-tip,
.no-more {
  padding: $spacing-lg;
  text-align: center;
  font-size: $font-size-sm;
  color: $text-tertiary;
}

.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-sm;
}

.load-more-tip {
  cursor: pointer;
  
  &:active {
    opacity: 0.7;
  }
}

.no-more {
  color: #CCCCCC;
}
</style>
