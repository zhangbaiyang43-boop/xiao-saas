<template>
  <view class="shop-header">
    <view class="shop-header-row">
      <image v-if="shopLogo" class="shop-logo" :src="shopLogo" mode="aspectFill" />
      <view v-else class="shop-logo shop-logo--placeholder">
        <text class="shop-logo-char">{{ logoChar }}</text>
      </view>
      <view class="shop-title-main">
        <view class="shop-name-row">
          <text class="shop-name">{{ shopName }}</text>
          <text class="shop-status" :class="{ 'shop-status--closed': storeClosed }">
            {{ storeClosed ? '已打烊' : '营业中' }}
          </text>
        </view>
        <view class="shop-chip-row">
          <view class="shop-chip shop-chip--table" @click="$emit('show-table-hint')">
            <text class="shop-chip-text">{{ tableDisplayText }}</text>
            <text class="shop-chip-arrow iconfont icon-roundright"></text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
// 门店头条（方案 B）：Logo + 店名 + 营业状态 + 桌号/堂食芯片 + 轻量副文案。
// 纯展示，点击桌号芯片只 emit show-table-hint，逻辑仍在 menu.vue。
export default {
  name: 'ShopHeader',
  props: {
    shopLogo: { type: String, default: '' },
    shopName: { type: String, default: '' },
    tableDisplayText: { type: String, default: '' },
    storeClosed: { type: Boolean, default: false },
  },
  emits: ['show-table-hint'],
  computed: {
    logoChar() {
      const name = String(this.shopName || '').trim()
      return name ? name.slice(0, 1) : '店'
    },
  },
}
</script>

<style lang="scss">
.shop-header {
  position: relative;
  flex-shrink: 0;
  background: var(--bg-card);
  padding: 16rpx 32rpx;
  box-sizing: border-box;
}

.shop-header-row {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  gap: 20rpx;
  width: 100%;
  box-sizing: border-box;
}

.shop-logo {
  width: 88rpx;
  height: 88rpx;
  border-radius: 20rpx;
  flex-shrink: 0;
  background: #f0f2f5;
}

.shop-logo--placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #ffd89b, #e17055);
}

.shop-logo-char {
  color: #fff;
  font-size: 36rpx;
  font-weight: 700;
  line-height: 1;
}

.shop-title-main {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
}

.shop-name-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  min-width: 0;
}

.shop-name {
  flex: 1;
  min-width: 0;
  color: var(--text-1, #1a1a1a);
  font-size: 34rpx;
  font-weight: 700;
  line-height: 48rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shop-status {
  flex-shrink: 0;
  padding: 2rpx 12rpx;
  border-radius: 8rpx;
  font-size: 22rpx;
  font-weight: 600;
  line-height: 32rpx;
  color: var(--brand);
  background: rgba(7, 193, 96, 0.12);
}

.shop-status--closed {
  color: var(--text-3);
  background: #f0f2f5;
}

.shop-chip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12rpx;
  margin-top: 8rpx;
}

.shop-chip {
  display: inline-flex;
  align-items: center;
  gap: 4rpx;
  height: 48rpx;
  padding: 0 16rpx;
  border-radius: 12rpx;
  box-sizing: border-box;
}

.shop-chip--table {
  background: var(--ink);
}

.shop-chip--table .shop-chip-text,
.shop-chip--table .shop-chip-arrow {
  color: #fff;
}

.shop-chip-text {
  font-size: 24rpx;
  font-weight: 600;
  line-height: 1;
}

.shop-chip-arrow {
  font-size: 22rpx;
  line-height: 1;
  opacity: 0.75;
}
</style>
