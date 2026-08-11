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
            <price-text
              size="md"
              :amount="dishPriceText(featuredDish)"
              :suffix="dishPriceSuffix(featuredDish)"
            />
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
import PriceText from './PriceText.vue'

export default {
  name: 'HomeTab',
  components: { PriceText },
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

<style lang="scss">
.ht-status-badge {
  padding: 6rpx 20rpx; border-radius: 999rpx; font-size: 22rpx; font-weight: 600;
}


.ht-status-badge--open { background: #d1fae5; color: #065f46; }


.ht-status-badge--closed { background: #fee2e2; color: #991b1b; }




.home-tab {
  padding: var(--page-pad) var(--page-pad) calc(132rpx + env(safe-area-inset-bottom));
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: var(--card-gap);
  box-sizing: border-box;
}



.ht-status-card {
  margin: 0;
  padding: 36rpx;
  background: var(--bg-card);
  border-radius: var(--radius-card);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24rpx;
  box-shadow: 0 8rpx 24rpx rgba(17, 24, 39, 0.04);
  box-sizing: border-box;
}



.ht-status-main { flex: 1; min-width: 0; }


.ht-store-name {
  display: block;
  font-size: 40rpx;
  line-height: 50rpx;
  font-weight: 700;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}


.ht-status-desc {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  line-height: 36rpx;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}


.ht-status-badge {
  flex-shrink: 0;
  min-height: 48rpx;
  padding: 0 20rpx;
  border-radius: 999rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  line-height: 34rpx;
  font-weight: 700;
}


.ht-status-badge--open { background: #E8F8EF; color: #087A3D; }


.ht-status-badge--closed { background: #F1F3F5; color: var(--text-3); }



.ht-order-card {
  margin: 0;
  padding: 36rpx;
  border-radius: var(--radius-hero);
  background: var(--brand) url('/static/order/home-hero-bg.jpg') left center / cover no-repeat;
  color: var(--text-inverse);
  box-sizing: border-box;
  transition: transform 120ms ease-out, opacity 120ms ease-out;
}


.ht-order-card:active { transform: scale(0.992); }


.ht-order-card--disabled { opacity: 0.72; }


.ht-order-card--disabled:active { transform: none; }


.ht-order-kicker {
  display: block;
  font-size: 24rpx;
  line-height: 34rpx;
  color: rgba(58,38,18,0.75);
  font-weight: 600;
}


.ht-order-title {
  display: block;
  margin-top: 8rpx;
  font-size: 48rpx;
  line-height: 64rpx;
  color: #2b1c0f;
  font-weight: 800;
}


.ht-order-desc {
  display: block;
  margin-top: 12rpx;
  font-size: 28rpx;
  line-height: 40rpx;
  color: rgba(58,38,18,0.78);
}


.ht-order-coupon {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  line-height: 34rpx;
  color: rgba(58,38,18,0.75);
}


.ht-order-btn {
  margin-top: 32rpx;
  width: 100%;
  height: var(--btn-primary-height);
  border-radius: var(--btn-primary-radius);
  background: var(--bg-card);
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}


.ht-order-btn text {
  color: var(--brand);
  font-size: var(--btn-primary-font-size);
  line-height: 1.2;
  font-weight: var(--btn-primary-font-weight);
}


.ht-order-btn--disabled { background: rgba(255,255,255,0.82); }


.ht-order-btn--disabled text { color: var(--text-3); }



.ht-section { display: flex; flex-direction: column; gap: var(--card-gap); }


.ht-section-head { display: flex; flex-direction: column; gap: 4rpx; }


.ht-section-head--row { flex-direction: row; align-items: center; justify-content: space-between; gap: 20rpx; }


.ht-section-title {
  display: block;
  margin: 0;
  font-size: 34rpx;
  line-height: 46rpx;
  font-weight: 800;
  color: var(--text-1);
}


.ht-section-sub {
  display: block;
  font-size: 24rpx;
  line-height: 34rpx;
  color: var(--text-3);
}


.ht-section-action {
  flex-shrink: 0;
  font-size: 26rpx;
  line-height: 38rpx;
  color: var(--brand);
  font-weight: 700;
}



.ht-feature-card {
  padding: 24rpx;
  background: var(--bg-card);
  border-radius: var(--radius-card);
  display: flex;
  gap: 24rpx;
  box-sizing: border-box;
}


.ht-feature-img-wrap {
  width: 192rpx;
  height: 192rpx;
  border-radius: 28rpx;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--border);
}


.ht-feature-img { width: 100%; height: 100%; display: block; }


.ht-feature-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F5F3EE;
}


.ht-feature-placeholder-img {
  width: 55%;
  height: 55%;
}


.ht-feature-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }


.ht-feature-title-row { display: flex; align-items: center; gap: 12rpx; min-width: 0; }


.ht-feature-name {
  flex: 1;
  min-width: 0;
  font-size: 36rpx;
  line-height: 48rpx;
  font-weight: 800;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}


.ht-feature-tag {
  flex-shrink: 0;
  height: 36rpx;
  padding: 0 14rpx;
  border-radius: 18rpx;
  background: #E8F8EF;
  color: #087A3D;
  font-size: 22rpx;
  line-height: 36rpx;
  font-weight: 700;
}


.ht-feature-desc {
  margin-top: 10rpx;
  font-size: 26rpx;
  line-height: 38rpx;
  color: var(--text-3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}


.ht-feature-bottom { margin-top: auto; display: flex; align-items: flex-end; justify-content: space-between; gap: 16rpx; }


.ht-feature-add {
  flex-shrink: 0;
  height: 72rpx;
  padding: 0 30rpx;
  border-radius: 36rpx;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease-out;
}


.ht-feature-add:active { transform: scale(0.96); }


.ht-feature-add text { color: var(--text-inverse); font-size: 26rpx; line-height: 36rpx; font-weight: 800; }


.ht-feature-add--disabled { background: #D0D5DD; }


.ht-feature-add--disabled:active { transform: none; }



.ht-last-list { display: flex; flex-wrap: wrap; gap: 16rpx; }


.ht-last-chip {
  max-width: 100%;
  min-height: 68rpx;
  padding: 0 22rpx 0 26rpx;
  border-radius: 34rpx;
  background: var(--bg-card);
  border: 1rpx solid #E5E8EB;
  display: flex;
  align-items: center;
  gap: 10rpx;
  box-sizing: border-box;
}


.ht-last-chip--disabled { opacity: 0.55; }


.ht-last-name {
  max-width: 220rpx;
  font-size: 26rpx;
  line-height: 36rpx;
  color: var(--text-1);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media screen and (max-width: 340px) {
  .home-tab { padding-left: 24rpx; padding-right: 24rpx; }
  .ht-status-card, .ht-order-card { padding: 30rpx; }
  .ht-feature-card { gap: 18rpx; padding: 20rpx; }
  .ht-feature-img-wrap { width: 176rpx; height: 176rpx; }
  .ht-feature-add { padding: 0 22rpx; }
  .ht-feature-add text { font-size: 24rpx; }
  .ht-last-name { max-width: 184rpx; }
}


.ht-last-add { color: var(--brand); font-size: 30rpx; line-height: 36rpx; font-weight: 900; }
</style>
