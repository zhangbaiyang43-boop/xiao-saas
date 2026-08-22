<template>
  <base-overlay :layer="layer" @mask-click="$emit('close')">
    <view class="base-sheet-surface" :class="$attrs.class">
      <view class="base-sheet-head" :class="{ 'base-sheet-head--leading': hasLeading }">
        <view v-if="hasLeading" class="base-sheet-head-leading">
          <slot name="header-left" />
        </view>
        <text class="base-sheet-title">{{ title }}</text>
        <text
          v-if="showClose"
          class="base-sheet-close iconfont icon-close"
          @click="$emit('close')"
        ></text>
      </view>
      <slot />
      <slot name="footer" />
    </view>
  </base-overlay>
</template>

<script>
import BaseOverlay from '@/components/base-overlay/base-overlay.vue'

const KNOWN_LAYERS = ['blocking', 'blocking-top', 'critical']

export default {
  name: 'BaseSheet',
  inheritAttrs: false,
  components: { BaseOverlay },
  options: {
    virtualHost: true,
  },
  props: {
    layer: {
      type: String,
      default: 'blocking',
      validator(value) {
        return KNOWN_LAYERS.includes(value)
      },
    },
    title: { type: String, default: '' },
    showClose: { type: Boolean, default: true },
  },
  emits: ['close'],
  computed: {
    hasLeading() {
      return Boolean(this.$slots['header-left'])
    },
  },
}
</script>

<style lang="scss">
.base-sheet-surface {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  background: #fff;
  border-radius: 32rpx 32rpx 0 0;
  padding: 0 0 calc(24rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
}

.base-sheet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 28rpx 36rpx 18rpx;
  border-bottom: 0;
  flex-shrink: 0;
  position: relative;
}

.base-sheet-head--leading {
  justify-content: center;
  min-height: 88rpx;
}

.base-sheet-head-leading {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
}

.base-sheet-title {
  font-size: 36rpx;
  font-weight: 800;
  color: var(--text-1);
  line-height: 1.2;
}

.base-sheet-close {
  width: 56rpx;
  height: 56rpx;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f3f4f6;
  color: var(--text-3);
  font-size: 28rpx;
}
</style>
