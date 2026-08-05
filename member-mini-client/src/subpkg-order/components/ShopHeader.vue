<template>
  <view class="shop-header">
    <view class="shop-header-row">
      <image v-if="shopLogo" class="shop-logo" :src="shopLogo" mode="aspectFill" />
      <view class="shop-title-main">
        <text class="shop-name">{{ shopName }}</text>
        <view class="shop-meta-row" @click="$emit('show-table-hint')">
          <text class="shop-table-text">{{ tableDisplayText }}</text>
          <text class="shop-meta-dot">·</text>
          <text class="shop-mode-text">{{ orderModeDisplayText }}</text>
          <text class="shop-meta-arrow iconfont icon-roundright"></text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的顶部门店信息栏（门店 logo/名称/桌号/点餐模式）。纯展示
// 组件，不带任何业务逻辑——点击都只 emit 出去，真正的处理函数还是原来
// menu.vue 里的 showTableHint，一行都没有改。
export default {
  name: 'ShopHeader',
  props: {
    shopLogo: { type: String, default: '' },
    shopName: { type: String, default: '' },
    tableDisplayText: { type: String, default: '' },
    orderModeDisplayText: { type: String, default: '' },
  },
  emits: ['show-table-hint'],
}
</script>

<style lang="scss">
.shop-header {
  position: relative;
  height: calc(220rpx + env(safe-area-inset-top));
  min-height: calc(220rpx + env(safe-area-inset-top));
  max-height: calc(220rpx + env(safe-area-inset-top));
  background: var(--brand) url('/static/order/shop-cover-default.jpg') right bottom / cover no-repeat;
  padding: calc(28rpx + env(safe-area-inset-top)) 32rpx 24rpx;
  box-sizing: border-box;
  overflow: hidden;
}



/* 门店封面图目前是通用素材，不分商户；等 admin-h5 有了真正的封面上传入口，
   这层叠加渐变可以继续用，只需要把 url() 换成商户自己的封面图。
   background-position 用 right bottom：这张图的餐桌/菜品在右下方，居中裁剪
   会把菜品裁掉一截、只剩空景。
   这张图本身左侧就是渐变到浅色的留白（跟首页"立即点餐"卡片同一张风格的图），
   之前又在上面叠了一层深绿色遮罩、文字还留白色——两层"提亮对比度"的手段叠加，
   把照片本身糊成一片。首页卡片那次是对的做法：不加遮罩，直接把文字换成深色，
   这里改成同一个做法，照片才能透出来，不然然会一直"雾蒙蒙"。 */

.shop-header-row {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 18rpx;
  height: 100%;
  max-width: calc(100vw - 220rpx);
  box-sizing: border-box;
}



.shop-logo {
  width: 80rpx;
  height: 80rpx;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2rpx solid rgba(255,255,255,0.65);
  background: rgba(255,255,255,0.15);
}



.shop-title-main {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
}



.shop-name {
  display: block;
  width: 100%;
  box-sizing: border-box;
  color: #2b1c0f;
  font-size: 36rpx;
  font-weight: 600;
  line-height: 50rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.shop-meta-row {
  min-height: 72rpx;
  margin-top: 4rpx;
  display: flex;
  align-items: center;
  width: fit-content;
  max-width: 100%;
  box-sizing: border-box;
}



.shop-table-text {
  color: #2b1c0f;
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 600;
  white-space: nowrap;
}



.shop-meta-dot {
  margin: 0 10rpx;
  color: rgba(58,38,18,0.6);
  font-size: 28rpx;
  line-height: 40rpx;
}



.shop-mode-text {
  color: rgba(58,38,18,0.78);
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 500;
  white-space: nowrap;
}



.shop-meta-arrow {
  margin-left: 10rpx;
  color: rgba(58,38,18,0.55);
  font-size: 28rpx;
  line-height: 40rpx;
  font-weight: 500;
}
</style>
