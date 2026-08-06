<template>
  <view class="menu-body">

    <scroll-view class="category-nav" scroll-y scroll-with-animation :scroll-top="categoryScrollTop">
      <view
        v-for="(cat, catIdx) in categories"
        :key="cat"
        :id="`cat-nav-${catIdx}`"
        class="cat-item"
        :class="{ active: activeCategory === cat }"
        @click="$emit('switch-category', cat)"
      >
        <view class="cat-icon-wrap"><text :class="['cat-icon', 'iconfont', categoryIconClass(cat)]"></text></view>
        <text class="cat-name">{{ categoryDisplayName(cat) }}</text>
      </view>
    </scroll-view>


    <scroll-view
      class="dish-scroll"
      scroll-y
      :scroll-into-view="scrollTarget"
      scroll-with-animation
      @scroll="handleScroll"
    >

      <view v-if="lastOrderItems.length" class="reorder-bar">
        <text class="reorder-label">再来一单</text>
        <scroll-view scroll-x class="reorder-scroll">
          <view class="reorder-chips">
            <view
              v-for="item in lastOrderItems"
              :key="item.name"
              class="reorder-chip"
              @click="$emit('reorder-item', item)"
            >
              <text class="reorder-chip-name">{{ item.name }}</text>
              <text class="reorder-chip-add">+</text>
            </view>
          </view>
        </scroll-view>
        <view class="reorder-all-btn" @click="$emit('reorder-all')">
          <text class="reorder-all-text">全部再来一份</text>
        </view>
      </view>

      <view v-if="!loading && !loadError && !allDishes.length" class="empty-menu">
        <image class="empty-menu-img" src="/static/order/empty-menu.png" mode="aspectFit" />
        <text class="empty-title">暂无菜品</text>
        <text class="empty-desc">菜单加载失败</text>
        <view class="empty-retry" @click="$emit('retry-load')"><text>重新加载</text></view>
      </view>
      <view v-for="(cat, catIdx) in categories" :key="cat" :id="`cat-sec-${catIdx}`">
        <view class="cat-divider"><view class="cat-divider-line"></view><view class="cat-divider-main"><text :class="['cat-divider-icon', 'iconfont', categoryIconClass(cat)]"></text><text class="cat-divider-text">{{ categoryDisplayName(cat) }}</text></view><view class="cat-divider-line"></view></view>
        <view
          v-for="(dish, dishIdx) in dishesByCategory(cat)"
          :key="dish.id"
          class="dish-item"
          :class="{ 'dish-item--featured': isFeatured(dish), 'dish-item--soldout': isSoldOut(dish) }"
          @click="$emit('open-product-detail', dish)"
        >
          <view class="dish-thumb">
            <image
              v-if="dishImage(dish) && !imageLoadFailed[dish.id]"
              class="dish-img"
              :src="dishImage(dish)"
              mode="aspectFill"
              lazy-load
              @error="$emit('image-error', dish.id)"
            />
            <view v-else class="dish-placeholder">
              <image class="dish-placeholder-img" src="/static/order/dish-placeholder.png" mode="aspectFit" />
            </view>
            <view v-if="isSoldOut(dish)" class="dish-soldout-mask"><text>已售罄</text></view>
          </view>
          <view class="dish-info">
            <view class="dish-title-row">
              <text class="dish-name">{{ dish.name }}</text>
              <view v-if="dishCardTags(dish).length" class="dish-tags">
                <text
                  v-for="tag in dishCardTags(dish)"
                  :key="tag"
                  class="dish-tag"
                  :class="isStrongDishTag(tag) ? 'dish-tag--strong' : 'dish-tag--plain'"
                >{{ tag }}</text>
              </view>
            </view>
            <view class="dish-meta">
              <text v-if="dishCardDesc(dish)" class="dish-desc">{{ dishCardDesc(dish) }}</text>
              <text v-if="showDishSales(dish)" class="dish-sales">月售{{ dish.sales_count }}</text>
            </view>
            <view class="dish-bottom-row">
              <view class="dish-price-wrap">
                <text class="dish-price-currency">¥</text>
                <text class="dish-price-amount">{{ dishPriceText(dish) }}</text>
                <text v-if="dishPriceSuffix(dish)" class="dish-price-suffix">{{ dishPriceSuffix(dish) }}</text>
              </view>
              <view class="dish-counter" @click.stop>
                <view v-if="isSoldOut(dish)" class="soldout-action" @click.stop><text>已售罄</text></view>
                <template v-else-if="hasSpecs(dish)">
                  <view v-if="dishOptionKindCount(dish.id) > 0" class="option-count-pill" @click.stop="$emit('open-cart')">
                    <text>{{ optionCountText(dish.id) }}</text>
                  </view>
                  <view class="choose-option-btn" @click.stop="$emit('open-spec-sheet', dish)">
                    <text>选规格</text>
                  </view>
                </template>
                <template v-else>
                  <view v-if="cartCount(dish.id) > 0" class="dish-qty-control">
                    <view class="counter-touch" @click.stop="$emit('remove-from-cart', dish)"><view class="counter-btn minus"><text class="iconfont icon-move"></text></view></view>
                    <text class="counter-num" :class="{ 'counter-num--pulse': qtyPulseKey === dish.id }">{{ cartCount(dish.id) }}</text>
                    <view class="counter-touch" @click.stop="$emit('add-to-cart', dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': addPressKey === dish.id }"><text class="iconfont icon-add"></text></view></view>
                  </view>
                  <view v-else class="counter-touch" @click.stop="$emit('add-to-cart', dish)"><view class="counter-btn plus" :class="{ 'counter-btn--pressing': addPressKey === dish.id }"><text class="iconfont icon-add"></text></view></view>
                </template>
              </view>
            </view>
          </view>
        </view>
      </view>
      <view class="list-pad" />
    </scroll-view>

  </view>
</template>

<script>
// 从 menu.vue 拆出来的菜品列表 + 分类导航区块（原来是 activeTab==='order' 那部
// 分模板：category-nav + dish-scroll，含"再来一单"、空菜单态、菜品卡片）。基本
// 是纯展示组件——切换分类（点击）、再来一单、加购物车、选规格、图片失败等动作
// 都只 emit 出去，真正的处理函数还是原来 menu.vue 里那几个
// （switchCategory/reorderItem/reorderAll/loadMenu/openCart/openSpecSheet/
// addToCart/removeFromCart/markDishImageFailed/openProductDetail），一行都
// 没有改。
//
// 唯一的例外：滚动时"左侧分类自动跟着高亮"这部分逻辑（原来的 onDishScroll）
// 挪进了这个组件自己内部，而不是像其它逻辑一样留在 menu.vue 里再靠 emit 转发。
// 原因：这段逻辑要用 uni.createSelectorQuery() 去查 .dish-scroll 和 #cat-sec-N
// 这些节点的实时位置——这些节点现在是本组件内部的模板节点，选择器查询必须用
// .in(this) 明确绑定到本组件实例才能可靠地查到自己内部的节点，不能指望不带
// .in() 的页面级查询穿透自定义组件边界（试过了，实测会查不到，导致滚动时左侧
// 分类不跟着高亮）。所以把这段查询逻辑一起挪进来，查完只把"当前应该高亮哪个
// 分类"这个结论通过 active-category-change emit 出去，真正的赋值
// （activeCategory.value = cat）还是父组件做，不在这里直接改父组件状态。
export default {
  name: 'DishList',
  props: {
    categories: { type: Array, default: () => [] },
    activeCategory: { type: String, default: '' },
    categoryScrollTop: { type: Number, default: 0 },
    scrollTarget: { type: String, default: '' },
    lastOrderItems: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    loadError: { type: Boolean, default: false },
    allDishes: { type: Array, default: () => [] },
    imageLoadFailed: { type: Object, default: () => ({}) },
    qtyPulseKey: { type: String, default: '' },
    addPressKey: { type: String, default: '' },
    ignoreScroll: { type: Boolean, default: false },
    // 纯查询/格式化函数直接从父组件原样传进来（不是在这里重写一份同名逻辑）。
    categoryIconClass: { type: Function, required: true },
    categoryDisplayName: { type: Function, required: true },
    dishesByCategory: { type: Function, required: true },
    isFeatured: { type: Function, required: true },
    isSoldOut: { type: Function, required: true },
    dishImage: { type: Function, required: true },
    dishCardTags: { type: Function, required: true },
    isStrongDishTag: { type: Function, required: true },
    dishCardDesc: { type: Function, required: true },
    showDishSales: { type: Function, required: true },
    dishPriceText: { type: Function, required: true },
    dishPriceSuffix: { type: Function, required: true },
    dishOptionKindCount: { type: Function, required: true },
    optionCountText: { type: Function, required: true },
    cartCount: { type: Function, required: true },
    hasSpecs: { type: Function, required: true },
  },
  emits: [
    'switch-category',
    'active-category-change',
    'reorder-item',
    'reorder-all',
    'retry-load',
    'open-cart',
    'open-spec-sheet',
    'image-error',
    'open-product-detail',
    'remove-from-cart',
    'add-to-cart',
  ],
  data() {
    return { scrollThrottleTimer: null }
  },
  methods: {
    handleScroll() {
      if (this.ignoreScroll) return
      if (this.scrollThrottleTimer) return
      this.scrollThrottleTimer = setTimeout(() => {
        this.scrollThrottleTimer = null
        const cats = this.categories
        if (!cats.length) return
        const query = uni.createSelectorQuery().in(this)
        query.select('.dish-scroll').boundingClientRect()
        cats.forEach((_, i) => query.select('#cat-sec-' + i).boundingClientRect())
        query.exec((res) => {
          const svRect = res[0]
          if (!svRect || svRect.height <= 0) return
          let current = cats[0]
          for (let i = 0; i < cats.length; i++) {
            const r = res[i + 1]
            if (r && typeof r.top === 'number' && (r.top - svRect.top) <= 30) current = cats[i]
          }
          if (current !== this.activeCategory) {
            this.$emit('active-category-change', current)
          }
        })
      }, 150)
    },
  },
}
</script>

<style lang="scss">
@import '../styles/_shared.scss';

.menu-body {
  display: flex;
  flex: 1;
  width: 100%;
  min-width: 0;
  /* 不能设 overflow:hidden——小程序的渲染引擎会把 overflow:hidden 祖先当成"裁剪边界"，
     连它里面 position:fixed 的弹层（确认订单、优惠券选择等）也一起裁掉，跟标准浏览器里
     position:fixed 应该完全无视祖先 overflow 裁剪的行为不一样。这些弹层要铺满到屏幕最
     底部，一旦被 menu-body 自己的高度边界裁掉，最下面的按钮就会看不见（这次反馈的问题）。
     侧栏分类和菜品列表各自已经自己声明了 overflow-y:auto，靠的是 min-height:0 这个
     flex 属性让它们在受限布局里能正常滚动，不依赖 menu-body 自己的 overflow，去掉它
     不影响任何滚动区域。 */
  overflow: visible;
  min-height: 0;
}



.category-nav {
  width: 168rpx;
  flex: 0 0 168rpx;
  background: #F6F7F8;
  overflow-x: hidden;
  overflow-y: auto;
  box-sizing: border-box;
}



.cat-item {
  position: relative;
  height: 108rpx;
  min-height: 108rpx;
  padding: 12rpx 10rpx 10rpx 14rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6rpx;
  text-align: center;
  color: #6F7680;
  background: transparent;
}



.cat-icon-wrap {
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  flex-shrink: 0;
}



.cat-icon {
  color: #9CA3AF;
  font-size: 32rpx;
  line-height: 36rpx;
}



.cat-name {
  max-width: 124rpx;
  font-size: 24rpx;
  line-height: 30rpx;
  font-weight: 600;
  color: #6F7680;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cat-item.active {
  background: #fff;
}

.cat-item.active .cat-icon-wrap {
  background: var(--brand-light);
}

.cat-item.active .cat-icon,
.cat-item.active .cat-name {
  color: var(--brand);
}

.cat-item.active .cat-name {
  font-weight: 800;
}

.cat-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 6rpx;
  height: 52rpx;
  border-radius: 0 4rpx 4rpx 0;
  background: var(--brand);
}

.cat-title {
  display: block;
  padding: 24rpx 0 16rpx;
  font-size: 24rpx;
  font-weight: 700;
  color: var(--text-3);
}



.dish-scroll {
  flex: 1;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--bg-page);
  padding: 0;
  box-sizing: border-box;
}



.cat-divider {
  height: 64rpx;
  padding: 0 24rpx;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}


.cat-divider-line {
  flex: 1;
  max-width: 160rpx;
  height: 1rpx;
  background: #E7E9EC;
}


.cat-divider-main {
  margin: 0 18rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  min-width: 0;
}



.cat-divider-icon {
  flex-shrink: 0;
  font-size: 28rpx;
  line-height: 32rpx;
  color: var(--brand);
}



.cat-divider-text {
  max-width: 168rpx;
  font-size: 26rpx;
  color: var(--text-3);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0;
}



.dish-item {
  display: flex;
  align-items: stretch;
  min-width: 0;
  height: 236rpx;
  min-height: 236rpx;
  max-height: 236rpx;
  margin: 0 20rpx 16rpx;
  padding: 20rpx 20rpx 20rpx 24rpx;
  box-sizing: border-box;
  background: #fff;
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  position: relative;
  overflow: hidden;
  transition: background 120ms ease, opacity 120ms ease;
}



.dish-item:active { background: #f8faf9; }


.dish-item--featured { border-left-color: transparent; }


.dish-item--soldout { opacity: .76; }



.dish-thumb {
  position: relative;
  width: 192rpx;
  height: 192rpx;
  border-radius: 20rpx;
  overflow: hidden;
  background: #F5F3EE;
  flex-shrink: 0;
  box-sizing: border-box;
  box-shadow: 0 2rpx 8rpx rgba(17,24,39,0.08);
}



.dish-img { width: 100%; height: 100%; display: block; }


.dish-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: #F5F3EE; }


.dish-placeholder-img { width: 60%; height: 60%; }


.dish-soldout-mask { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(31,41,55,.42); }


.dish-soldout-mask text { min-width: 104rpx; height: 48rpx; padding: 0 18rpx; border-radius: 999rpx; display: flex; align-items: center; justify-content: center; background: rgba(17,24,39,.76); color: #fff; font-size: 24rpx; font-weight: 700; }




.reorder-bar {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin: 16rpx 20rpx 12rpx;
  padding: 16rpx 20rpx;
  border-radius: 20rpx;
  background: #fff;
  box-shadow: var(--card-shadow);
  box-sizing: border-box;
}



.reorder-label {
  font-size: 22rpx;
  color: var(--text-3);
  white-space: nowrap;
  flex-shrink: 0;
}



.reorder-scroll {
  flex: 1;
  white-space: nowrap;
}



.reorder-chips {
  display: flex;
  gap: 10rpx;
}



.reorder-chip {
  display: inline-flex;
  align-items: center;
  gap: 6rpx;
  padding: 8rpx 16rpx;
  border-radius: 32rpx;
  border: 1rpx solid var(--brand);
  background: #f0fdf4;
  flex-shrink: 0;
}



.reorder-chip-name {
  font-size: 22rpx;
  color: #065f46;
  max-width: 120rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.reorder-chip-add {
  font-size: 24rpx;
  color: var(--brand);
  font-weight: 800;
  line-height: 1;
}



.reorder-all-btn {
  flex-shrink: 0;
  background: var(--brand);
  border-radius: 28rpx;
  padding: 6rpx 18rpx;
}



.reorder-all-text {
  font-size: 22rpx;
  color: #fff;
  font-weight: 700;
  white-space: nowrap;
}




.dish-info { flex: 1; min-width: 0; display: flex; flex-direction: column; margin-left: 18rpx; box-sizing: border-box; overflow: hidden; }


.dish-title-row { display: flex; align-items: flex-start; gap: 8rpx; min-width: 0; }


.dish-name { flex: 1; min-width: 0; font-size: 32rpx; font-weight: 600; line-height: 44rpx; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.dish-tags { display: flex; flex-shrink: 0; flex-wrap: nowrap; max-width: 88rpx; overflow: hidden; }


.dish-tag { max-width: 88rpx; height: 34rpx; padding: 0 8rpx; border-radius: 8rpx; box-sizing: border-box; font-size: 20rpx; font-weight: 500; line-height: 34rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tag--strong { color: #078546; background: #e9f9f0; }
.dish-tag--plain { display: none; }


.dish-meta { flex: 1; min-width: 0; min-height: 0; padding-top: 6rpx; }


.dish-desc { display: block; min-width: 0; font-size: 26rpx; color: var(--text-3); line-height: 36rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.dish-sales { display: block; min-width: 0; margin-top: 2rpx; margin-left: 0; font-size: 24rpx; line-height: 34rpx; color: #A8ADB4; font-weight: 400; }


.dish-bottom-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 0; margin-top: auto; min-width: 0; }


.dish-price-wrap { flex: 1; min-width: 104rpx; overflow: hidden; display: flex; align-items: baseline; color: var(--brand); }


.dish-price-currency { flex-shrink: 0; font-size: 24rpx; font-weight: 700; line-height: 1; }


.dish-price-amount { min-width: 0; font-size: 40rpx; font-weight: 700; line-height: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.dish-price-suffix { flex-shrink: 0; margin-left: 2rpx; font-size: 22rpx; font-weight: 500; line-height: 1; color: var(--brand); }


.dish-counter { flex: none; display: flex; align-items: center; justify-content: flex-end; flex-shrink: 0; margin-left: 6rpx; min-width: 60rpx; max-width: 176rpx; padding-right: 0; box-sizing: border-box; }


.dish-qty-control { width: 164rpx; max-width: 164rpx; height: 58rpx; padding: 4rpx; display: flex; align-items: center; justify-content: space-between; gap: 0; overflow: hidden; flex-shrink: 0; box-sizing: border-box; border-radius: 29rpx; background: #F3F4F6; }


.counter-touch { width: 72rpx; height: 72rpx; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; }


.dish-qty-control .counter-touch { width: 50rpx; height: 50rpx; }


.dish-counter > .counter-touch { width: 76rpx; height: 76rpx; }


.dish-qty-control .counter-btn--pressing { animation: none; transform: none; }

.dish-counter .counter-btn { width: 60rpx; height: 60rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-sizing: border-box; flex-shrink: 0; }
.dish-qty-control .counter-btn { width: 50rpx; height: 50rpx; }
.dish-counter .counter-btn text { font-size: 30rpx; font-weight: 800; line-height: 1; }
.dish-counter .counter-btn .iconfont { font-size: 27rpx; font-weight: 400; line-height: 1; }
.dish-counter .counter-btn.plus { background: var(--brand); }
.dish-counter .counter-btn.plus text { color: #fff; }
.dish-counter .counter-btn.minus { border: none; background: #E5E7EB; }
.dish-qty-control .counter-btn.minus { background: #EAEDF1; }
.dish-counter .counter-btn.minus text { color: #4B5563; }
.dish-counter .counter-num { width: 36rpx; min-width: 36rpx; text-align: center; font-size: 30rpx; line-height: 32rpx; font-weight: 600; color: var(--text-1); }
.dish-qty-control .counter-num { width: 32rpx; min-width: 32rpx; font-size: 30rpx; line-height: 32rpx; }


.soldout-action { height: 60rpx; min-width: 104rpx; padding: 0 20rpx; border-radius: 30rpx; display: flex; align-items: center; justify-content: center; background: #eef1f4; box-sizing: border-box; flex-shrink: 0; }


.soldout-action text { font-size: 24rpx; font-weight: 600; color: #9aa1aa; white-space: nowrap; }




.list-pad { height: calc(348rpx + env(safe-area-inset-bottom)); }



.empty-menu {
  min-height: 520rpx;
  padding: 80rpx 32rpx 32rpx;
  text-align: center;
  box-sizing: border-box;
}



.empty-menu-img {
  width: 280rpx;
  height: 280rpx;
  margin: 0 auto 8rpx;
}



.empty-title {
  display: block;
  color: var(--text-1);
  font-size: 34rpx;
  font-weight: 800;
}



.empty-desc {
  display: block;
  margin-top: 14rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 1.6;
}



.empty-retry {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 28rpx;
  padding: 0 36rpx;
  height: 72rpx;
  border-radius: 36rpx;
  background: var(--brand);
  text { color: #fff; font-size: 28rpx; font-weight: 700; }
}



.choose-option-btn { height: 60rpx; padding: 0 20rpx; border-radius: 30rpx; background: var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; transition: transform 180ms var(--bounce-ease); text { color: #fff; font-size: 24rpx; font-weight: 600; white-space: nowrap; } }


.choose-option-btn:active { transform: scale(.97); }


.option-count-pill { position: static; min-width: 34rpx; height: 34rpx; padding: 0 10rpx; border-radius: 999rpx; background: #fff; border: 2rpx solid var(--brand); display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-sizing: border-box; text { color: var(--brand); font-size: 20rpx; font-weight: 800; white-space: nowrap; } }



.counter-btn--pressing {
  animation: addButtonPress 220ms var(--bounce-ease);
}

@keyframes addButtonPress {
  0% { transform: scale(1); }
  40% { transform: scale(.9); }
  75% { transform: scale(1.08); }
  100% { transform: scale(1); }
}
</style>
