<template>
  <view class="home-tab">
    <view class="ht-status-card">
      <view class="ht-status-main">
        <text class="ht-store-name">{{ shopName }}</text>
        <text class="ht-status-desc">{{ homeStatusDesc }}</text>
      </view>
      <view :class="['ht-status-badge', storeClosed ? 'ht-status-badge--closed' : 'ht-status-badge--open']">
        <text>{{ storeClosed ? '休息中' : '营业中' }}</text>
      </view>
    </view>

    <view class="ht-order-card" :class="{ 'ht-order-card--disabled': !canStartOrdering }" @click="$emit('start-order')">
      <text class="ht-order-kicker">今日推荐</text>
      <text class="ht-order-title">立即点餐</text>
      <text class="ht-order-desc">{{ homeStatusDesc }}</text>
      <text v-if="homeCouponHint" class="ht-order-coupon">{{ homeCouponHint }}</text>
      <view class="ht-order-btn" :class="{ 'ht-order-btn--disabled': !canStartOrdering }" @click.stop="$emit('start-order')">
        <text>{{ homeOrderButtonText }}</text>
      </view>
    </view>

    <view v-if="featuredDish" class="ht-section">
      <view class="ht-section-head">
        <text class="ht-section-title">店长推荐</text>
        <text class="ht-section-sub">精选招牌菜品</text>
      </view>
      <view class="ht-feature-card" @click="$emit('open-product-detail', featuredDish)">
        <view class="ht-feature-img-wrap">
          <image
            v-if="dishImage(featuredDish) && !imageLoadFailed[featuredDish.id]"
            class="ht-feature-img"
            :src="dishImage(featuredDish)"
            mode="aspectFill"
            @error="$emit('image-error', featuredDish.id)"
          />
          <view v-else class="ht-feature-placeholder">
            <image class="ht-feature-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
          </view>
        </view>
        <view class="ht-feature-info">
          <view class="ht-feature-title-row">
            <text class="ht-feature-name">{{ featuredDish.name }}</text>
            <text v-if="featuredDishTag" class="ht-feature-tag">{{ featuredDishTag }}</text>
          </view>
          <text v-if="dishCardDesc(featuredDish)" class="ht-feature-desc">{{ dishCardDesc(featuredDish) }}</text>
          <view class="ht-feature-bottom">
            <view class="ht-feature-price">
              <text class="ht-feature-yen">¥</text>
              <text class="ht-feature-amount">{{ dishPriceText(featuredDish) }}</text>
              <text v-if="dishPriceSuffix(featuredDish)" class="ht-feature-suffix">{{ dishPriceSuffix(featuredDish) }}</text>
            </view>
            <view
              class="ht-feature-add"
              :class="{ 'ht-feature-add--disabled': !canHomeAdd }"
              @click.stop="$emit('featured-add')"
            >
              <text>{{ hasSpecs(featuredDish) ? '选规格' : '直接加入' }}</text>
            </view>
          </view>
        </view>
      </view>
    </view>

    <view v-if="homeLastOrderItems.length" class="ht-section">
      <view class="ht-section-head ht-section-head--row">
        <text class="ht-section-title">再来一单</text>
        <text class="ht-section-action" @click="$emit('reorder-all')">全部再来一份</text>
      </view>
      <view class="ht-last-list">
        <view
          v-for="item in homeLastOrderItems"
          :key="item.key"
          class="ht-last-chip"
          :class="{ 'ht-last-chip--disabled': storeClosed }"
          @click="$emit('reorder-item', item)"
        >
          <text class="ht-last-name">{{ item.name }}</text>
          <text class="ht-last-add">+</text>
        </view>
      </view>
    </view>

  </view>
</template>

<script>
// 从 menu.vue 拆出来的首页 Tab 区块（原来是 activeTab==='home' 那一段模板）。
// 纯展示组件，不带任何业务逻辑——所有需要改父组件状态的动作（去点餐、查看菜品
// 详情、加入购物车、再来一单）都只 emit 出去，真正的处理函数还是原来 menu.vue
// 里那几个（handleHomeStartOrder/openProductDetail/handleFeaturedAdd/
// markDishImageFailed/handleHomeReorderItem/handleHomeReorderAll），一行都
// 没有改，只是从内联模板换成了从父组件监听事件调用。
export default {
  name: 'HomeTab',
  props: {
    shopName: { type: String, default: '' },
    homeStatusDesc: { type: String, default: '' },
    storeClosed: { type: Boolean, default: false },
    canStartOrdering: { type: Boolean, default: false },
    homeCouponHint: { type: String, default: '' },
    homeOrderButtonText: { type: String, default: '' },
    featuredDish: { type: Object, default: null },
    featuredDishTag: { type: String, default: '' },
    canHomeAdd: { type: Boolean, default: false },
    homeLastOrderItems: { type: Array, default: () => [] },
    imageLoadFailed: { type: Object, default: () => ({}) },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑），
    // 保证跟父组件其它地方用到的结果 100% 一致。
    dishImage: { type: Function, required: true },
    dishCardDesc: { type: Function, required: true },
    dishPriceText: { type: Function, required: true },
    dishPriceSuffix: { type: Function, required: true },
    hasSpecs: { type: Function, required: true },
  },
  emits: ['start-order', 'open-product-detail', 'featured-add', 'image-error', 'reorder-item', 'reorder-all'],
}
</script>
