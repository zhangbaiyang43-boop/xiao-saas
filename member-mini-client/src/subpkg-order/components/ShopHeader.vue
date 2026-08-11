<template>
  <view class="shop-header">
    <view class="shop-header-row">
      <image
        v-if="shopLogo && !logoFailed"
        class="shop-logo"
        :src="shopLogo"
        mode="aspectFill"
        @error="logoFailed = true"
      />
      <view v-else class="shop-logo shop-logo--placeholder">
        <image class="shop-logo-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
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
          <view class="shop-chip shop-chip--mode">
            <text class="shop-chip-text">{{ orderModeDisplayText }}</text>
          </view>
        </view>
        <view v-if="dishCount > 0 || couponCount > 0" class="shop-sub-row">
          <text v-if="dishCount > 0" class="shop-sub-item">
            今日可点 <text class="shop-sub-em">{{ dishCount }}</text> 道
          </text>
          <text v-if="couponCount > 0" class="shop-sub-item">
            优惠券 <text class="shop-sub-em">{{ couponCount }}</text> 张可用
          </text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
// 门店头条（方案1+B）：全宽 Logo + 店名 + 桌号芯片。纯展示。
// 布局剧本见 menu.vue 模板注释——不要把头塞回右侧 scroll。
export default {
  name: 'ShopHeader',
  props: {
    shopLogo: { type: String, default: '' },
    shopName: { type: String, default: '' },
    tableDisplayText: { type: String, default: '' },
    orderModeDisplayText: { type: String, default: '' },
    storeClosed: { type: Boolean, default: false },
    dishCount: { type: Number, default: 0 },
    couponCount: { type: Number, default: 0 },
  },
  emits: ['show-table-hint'],
  data() {
    return { logoFailed: false }
  },
  watch: {
    shopLogo() {
      this.logoFailed = false
    },
  },
}
</script>

<style lang="scss">
.shop-header {
  position: relative;
  flex-shrink: 0;
  background: var(--bg-card);
  padding: 24rpx var(--page-pad) 20rpx;
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
  background: var(--bg-muted);
}

.shop-logo--placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F5F3EE;
}

.shop-logo-placeholder-img {
  width: 60%;
  height: 60%;
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
  color: var(--text-1, var(--ink));
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
  color: var(--brand-dark);
  background: var(--brand-light);
}

.shop-status--closed {
  color: var(--text-3);
  background: var(--bg-muted);
}

.shop-chip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12rpx;
  margin-top: 12rpx;
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
  color: var(--text-inverse);
}

.shop-chip--mode {
  background: var(--bg-muted);
}

.shop-chip--mode .shop-chip-text {
  color: var(--text-2);
  font-weight: 500;
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

.shop-sub-row {
  display: flex;
  flex-wrap: wrap;
  gap: 20rpx;
  margin-top: 12rpx;
}

.shop-sub-item {
  font-size: 22rpx;
  color: var(--text-3);
  line-height: 32rpx;
}

.shop-sub-em {
  color: var(--text-2);
  font-weight: 600;
}
</style>
