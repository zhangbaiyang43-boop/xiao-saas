<template>
  <view class="menu-body">

    <scroll-view class="category-nav" scroll-y scroll-with-animation :scroll-top="categoryScrollTop">
      <view
        v-for="cat in categories"
        :key="cat"
        :id="`cat-nav-${categoryAnchorId(cat)}`"
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
      @scroll="onDishScroll"
    >

      <slot name="header"></slot>

      <view v-if="lastOrderItems.length" class="reorder-bar">
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
          <text class="iconfont icon-return reorder-all-icon"></text>
        </view>
      </view>

      <view v-if="!loading && !loadError && !allDishes.length" class="empty-menu">
        <state-empty
          title="暂无菜品"
          desc="当前没有可点的菜品"
          action-text="重新加载"
          @action="$emit('retry-load')"
        >
          <template #icon>
            <image class="empty-menu-img" src="/static/order/empty-menu.png" mode="aspectFit" />
          </template>
        </state-empty>
      </view>
      <view v-for="cat in categories" :key="cat" :id="categoryAnchorId(cat)">
        <view class="cat-divider"><view class="cat-divider-line"></view><view class="cat-divider-main"><text :class="['cat-divider-icon', 'iconfont', categoryIconClass(cat)]"></text><text class="cat-divider-text">{{ categoryDisplayName(cat) }}</text></view><view class="cat-divider-line"></view></view>
        <dish-card
          v-for="dish in dishesByCategory(cat)"
          :key="dish.id"
          :model="buildDishCardModel(dish)"
          @open-detail="$emit('open-product-detail', $event)"
          @image-error="$emit('image-error', $event)"
          @open-cart="$emit('open-cart')"
          @open-spec="$emit('open-spec-sheet', $event)"
          @remove="$emit('remove-from-cart', $event)"
          @add="$emit('add-to-cart', $event)"
        />
      </view>
      <view class="list-pad" />
    </scroll-view>

  </view>
</template>

<script>
import { categoryAnchorId } from '../composables/useDishCategories.js'
import StateEmpty from '@/components/state-empty/state-empty.vue'
import DishCard from './DishCard.vue'

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
//
// 另：scrollTop 会经 scroll-position 抛给父组件，用于方案1「全宽头部收起 /
// 迷你条显隐」；门店大头部不在本列表里，这里不做高度/透明度动画。
export default {
  name: 'DishList',
  components: { StateEmpty, DishCard },
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
    'scroll-position',
    'reorder-item',
    'reorder-all',
    'retry-load',
    'open-cart',
    'open-spec-sheet',
    'image-error',
    'open-product-detail',
    'remove-from-cart',
    'add-to-cart',
    'programmatic-scroll-settled',
  ],
  data() {
    return { scrollThrottleTimer: null }
  },
  beforeUnmount() {
    if (this.scrollThrottleTimer) {
      clearTimeout(this.scrollThrottleTimer)
      this.scrollThrottleTimer = null
    }
  },
  methods: {
    categoryAnchorId,
    buildDishCardModel(dish) {
      const id = dish?.id
      const tags = this.dishCardTags(dish).map((tag) => {
        const strong = this.isStrongDishTag(tag)
        return {
          text: tag,
          tone: strong ? 'brand' : 'neutral',
          emphasis: strong ? 'strong' : 'plain',
        }
      })
      return {
        id,
        dish,
        name: dish?.name || '',
        imageSrc: this.dishImage(dish),
        imageFailed: !!this.imageLoadFailed[id],
        description: this.dishCardDesc(dish),
        salesText: this.showDishSales(dish) ? '月售' + dish.sales_count : '',
        tags,
        priceAmount: this.dishPriceText(dish),
        priceSuffix: this.dishPriceSuffix(dish),
        featured: this.isFeatured(dish),
        soldOut: this.isSoldOut(dish),
        hasSpecs: this.hasSpecs(dish),
        quantity: this.cartCount(id),
        optionKindCount: this.dishOptionKindCount(id),
        optionCountText: this.optionCountText(id),
        addPressing: this.addPressKey === id,
        qtyPulsing: this.qtyPulseKey === id,
      }
    },
    // 方案1：门店大头部在 menu.vue 全宽区，不在本列表里。这里只把 scrollTop
    // 抛给父组件决定何时收起头部/露出迷你条；分类高亮仍走下面的节流逻辑。
    onDishScroll(e) {
      const scrollTop = e?.detail?.scrollTop
      if (typeof scrollTop === 'number') {
        this.$emit('scroll-position', scrollTop)
      }
      this.handleScroll()
    },
    handleScroll() {
      if (this.scrollThrottleTimer) return
      this.scrollThrottleTimer = setTimeout(() => {
        this.scrollThrottleTimer = null
        const cats = this.categories
        if (!cats.length) return
        const query = uni.createSelectorQuery().in(this)
        query.select('.dish-scroll').boundingClientRect()
        cats.forEach((cat) => query.select('#' + categoryAnchorId(cat)).boundingClientRect())
        query.exec((res) => {
          const svRect = res[0]
          if (!svRect || svRect.height <= 0) return
          let current = cats[0]
          for (let i = 0; i < cats.length; i++) {
            const r = res[i + 1]
            if (r && typeof r.top === 'number' && (r.top - svRect.top) <= 30) current = cats[i]
          }
          if (this.scrollTarget || this.ignoreScroll) {
            if (this.scrollTarget && categoryAnchorId(current) === this.scrollTarget) {
              this.$emit('programmatic-scroll-settled', current)
            }
            return
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
  width: 160rpx;
  flex: 0 0 160rpx;
  background: var(--bg-page);
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
  color: var(--text-3);
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
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cat-item.active {
  background: var(--bg-card);
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
}



.reorder-chip-add {
  font-size: 24rpx;
  color: var(--brand);
  font-weight: 800;
  line-height: 1;
}



.reorder-all-btn {
  flex-shrink: 0;
  width: 56rpx;
  height: 56rpx;
  background: var(--brand);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}



.reorder-all-icon {
  color: #fff;
  font-size: 28rpx;
  line-height: 1;
}




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



</style>
