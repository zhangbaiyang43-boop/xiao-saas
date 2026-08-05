import { computed } from 'vue'

// 从 menu.vue 拆出来的首页 Tab（HomeTab）展示逻辑——招牌菜推荐、"再来一单"预览
// 这些只读派生计算，以及"上次点过的这份历史记录，现在还能不能重新加入购物车"
// 的纯校验逻辑。逻辑跟原来在 menu.vue 里的一字未改，只是搬了个位置。
//
// 特意没有拆进来的东西，留在 menu.vue 里：
// - handleHomeStartOrder/handleFeaturedAdd/handleHomeReorderItem/handleHomeReorderAll/
//   reorderItem/reorderAll：这几个是真正"点一下就把菜加进购物车"的动作函数，会调用
//   addToCart/openSpecSheet 并触发 toast/震动反馈，属于会改动购物车这个跨功能共享状态
//   的操作，不是首页 Tab 自己的展示逻辑，留给购物车相关的组合式函数去接。
export function useHomeTabView({ allDishes, storeClosed, bannerInfo, myOrders, isSoldOut, dishTags, normalizeDishTag, hasSpecs }) {
  const homeRecommendedTags = ['招牌', '热销', '店长推荐', '新品']

  const isMenuEmpty = computed(() => allDishes.value.length <= 0)
  const canStartOrdering = computed(() => !storeClosed.value && !isMenuEmpty.value)
  const homeStatusDesc = computed(() => {
    if (isMenuEmpty.value) return '暂无可点菜品'
    return '共' + allDishes.value.length + '道菜可点'
  })
  const homeOrderButtonText = computed(() => {
    if (storeClosed.value) return '门店休息中'
    if (isMenuEmpty.value) return '暂无菜品'
    return '开始点餐'
  })
  const homeCouponHint = computed(() => {
    const count = Number(bannerInfo.value?.couponCount || 0)
    if (count <= 0) return ''
    return count + '张优惠券可用'
  })
  const featuredDish = computed(() => {
    if (isMenuEmpty.value) return null
    return allDishes.value.find(d => {
      if (isSoldOut(d)) return false
      const tags = dishTags(d).map(normalizeDishTag)
      return homeRecommendedTags.some(tag => tags.includes(normalizeDishTag(tag)))
    }) || null
  })
  const canHomeAdd = computed(() => !!featuredDish.value && !storeClosed.value && !isSoldOut(featuredDish.value))
  const featuredDishTag = computed(() => {
    if (!featuredDish.value) return ''
    const tags = dishTags(featuredDish.value).map(normalizeDishTag)
    if (tags.includes('招牌')) return '招牌'
    if (tags.includes('热销')) return '热销'
    if (tags.includes('新品')) return '新品'
    return ''
  })

  const dishMatchesHistoryItem = (dish, item) => String(dish.id) === String(item.id || item.dish_id || item.menu_item_id || '') || dish.name === item.name
  const findHistoryDish = (item) => allDishes.value.find(d => dishMatchesHistoryItem(d, item))
  const historyItemHasSpecSnapshot = (item) => !!(item?.specKey || item?.specLabel || item?.specifications?.length || /[闂?]/.test(String(item?.name || "")))
  const validateHistoryReorderItem = (item) => {
    const dish = findHistoryDish(item)
    if (!dish || isSoldOut(dish)) return { dish, reason: 'unavailable' }
    if (hasSpecs(dish) || historyItemHasSpecSnapshot(item)) return { dish, reason: 'spec_changed' }
    return { dish, reason: '' }
  }

  const lastOrderItems = computed(() => {
    const last = myOrders.value.find(o => !['cancelled', 'rejected'].includes(o.status))
    if (!last || !last.items) return []
    return last.items.slice(0, 6)
  })
  const homeLastOrderItems = computed(() => {
    if (isMenuEmpty.value) return []
    return lastOrderItems.value
      .map((item, index) => ({ ...item, dish: findHistoryDish(item), key: String(item.id || item.name || index) + '-' + index }))
      .filter(item => item.dish && !isSoldOut(item.dish))
      .slice(0, 4)
  })

  return {
    isMenuEmpty,
    canStartOrdering,
    homeStatusDesc,
    homeOrderButtonText,
    homeCouponHint,
    featuredDish,
    canHomeAdd,
    featuredDishTag,
    findHistoryDish,
    validateHistoryReorderItem,
    lastOrderItems,
    homeLastOrderItems,
  }
}
