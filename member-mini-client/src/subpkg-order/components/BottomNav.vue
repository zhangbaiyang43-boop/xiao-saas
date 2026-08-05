<template>
  <view class="bottom-nav">
    <view :class="['bn-item', { active: activeTab === 'home' }]" @click="$emit('switch-tab', 'home')">
      <text :class="['bn-icon', 'iconfont', activeTab === 'home' ? 'icon-homefill' : 'icon-home']"></text>
    </view>
    <view :class="['bn-item', { active: activeTab === 'order' }]" @click="$emit('switch-tab', 'order')">
      <text :class="['bn-icon', 'iconfont', activeTab === 'order' ? 'icon-shopfill' : 'icon-shop']"></text>
      <view v-if="totalCount > 0 && activeTab !== 'order'" class="bn-dot"></view>
    </view>
    <view :class="['bn-item', { active: activeTab === 'card' }]" @click="$emit('switch-to-card')">
      <text :class="['bn-icon', 'iconfont', activeTab === 'card' ? 'icon-likefill' : 'icon-like']"></text>
      <view v-if="bannerInfo && bannerInfo.couponCount > 0 && activeTab !== 'card'" class="bn-dot"></view>
    </view>
    <view :class="['bn-item', { active: activeTab === 'mine' }]" @click="$emit('go-mine')">
      <text :class="['bn-icon', 'iconfont', activeTab === 'mine' ? 'icon-myfill' : 'icon-my']"></text>
    </view>
  </view>
</template>

<script>
// 从 menu.vue 拆出来的底部四个 Tab 导航栏。纯展示组件，不带任何业务逻辑——原
// 模板里"首页""点餐"两个 Tab 是直接 @click="activeTab = 'xxx'" 的状态赋值，
// 这里改成 emit('switch-tab', 'xxx')，父组件监听后照原样赋值；"会员卡"
// "我的"两个本来就是调用命名函数（switchToCard/goMine），原样 emit 出去，
// 一行逻辑都没有改。
export default {
  name: 'BottomNav',
  props: {
    activeTab: { type: String, default: '' },
    totalCount: { type: Number, default: 0 },
    bannerInfo: { type: Object, default: null },
  },
  emits: ['switch-tab', 'switch-to-card', 'go-mine'],
}
</script>

<style lang="scss">
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(100rpx + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: #fff;
  border-top: 1rpx solid var(--border);
  display: flex;
  align-items: stretch;
  z-index: 300;
}



.bn-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;

  &:active { opacity: 0.72; }
}



.bn-icon {
  display: block;
  width: 60rpx;
  height: 60rpx;
  color: var(--text-3);
  font-size: 56rpx;
  line-height: 60rpx;
  text-align: center;
  transition: color 180ms ease-out, transform 180ms ease-out;
}



.bn-dot {
  position: absolute;
  top: 12rpx;
  right: calc(50% - 36rpx);
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: var(--danger);
}
</style>
