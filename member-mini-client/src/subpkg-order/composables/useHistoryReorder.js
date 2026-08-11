import { toastText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的"重新加入购物车"动作——首页"开始点餐"/推荐卡加购、
// 首页和菜单页的"再来一单"整单重放、点单个历史商品。之所以是 MEDIUM 而不是
// LOW：这几个函数会真的调用 addToCart/openSpecSheet 改动购物车，并触发
// toast/震动反馈，不是纯展示计算。addToCart/openSpecSheet/hasSpecs 通过
// 回调传入而不是直接 import，因为它们是购物车/规格那组状态自己的方法，这里
// 只是复用，不重新实现。uni 是 uni-app 全局 API，跟其他组合式函数一样直接用，
// 不需要 import。逻辑跟原来在 menu.vue 里的一字未改，只是搬了个位置。
export function useHistoryReorder({
  activeTab, storeClosed, canStartOrdering, canHomeAdd, featuredDish,
  validateHistoryReorderItem, homeLastOrderItems, lastOrderItems,
  hasSpecs, addToCart, openSpecSheet,
}) {
  const showHistoryReorderToast = ({ added = 0, skippedUnavailable = 0, skippedSpec = 0 }) => {
    if (added > 0) {
      let title = toastText.reorderAdded(added)
      if (skippedUnavailable > 0) title += toastText.reorderPartialUnavailable
      else if (skippedSpec > 0) title += toastText.reorderPartialSpec
      uni.showToast({ title, icon: 'none', duration: 1400 })
      return
    }
    if (skippedUnavailable > 0) {
      uni.showToast({ title: toastText.dishUnavailable, icon: 'none', duration: 1400 })
      return
    }
    if (skippedSpec > 0) {
      uni.showToast({ title: toastText.specChanged, icon: 'none', duration: 1400 })
      return
    }
    uni.showToast({ title: toastText.reorderEmpty, icon: 'none', duration: 1200 })
  }

  const handleHomeStartOrder = () => {
    if (!canStartOrdering.value) return
    activeTab.value = 'order'
  }
  const handleFeaturedAdd = () => {
    if (!canHomeAdd.value) return
    if (hasSpecs(featuredDish.value)) openSpecSheet(featuredDish.value)
    else addToCart(featuredDish.value)
  }
  const handleHomeReorderItem = (item) => {
    if (storeClosed.value) return
    const check = validateHistoryReorderItem(item)
    if (!check.dish || check.reason === 'unavailable') {
      uni.showToast({ title: toastText.dishUnavailable, icon: 'none', duration: 1200 })
      return
    }
    if (check.reason === 'spec_changed') {
      openSpecSheet(check.dish)
      uni.showToast({ title: toastText.specChanged, icon: 'none', duration: 1200 })
      return
    }
    addToCart(check.dish)
  }
  const handleHomeReorderAll = () => {
    if (storeClosed.value || !homeLastOrderItems.value.length) return
    let added = 0
    let skippedUnavailable = 0
    let skippedSpec = 0
    homeLastOrderItems.value.forEach(item => {
      const check = validateHistoryReorderItem(item)
      if (!check.dish || check.reason === 'unavailable') {
        skippedUnavailable += 1
        return
      }
      if (check.reason === 'spec_changed') {
        skippedSpec += 1
        return
      }
      addToCart(check.dish)
      added += 1
    })
    if (added > 0) uni.vibrateShort({ type: 'medium' })
    showHistoryReorderToast({ added, skippedUnavailable, skippedSpec })
  }

  const reorderItem = (item) => {
    const check = validateHistoryReorderItem(item)
    if (!check.dish || check.reason === 'unavailable') {
      uni.showToast({ title: toastText.dishUnavailable, icon: 'none', duration: 1200 })
      return
    }
    if (check.reason === 'spec_changed') {
      openSpecSheet(check.dish)
      uni.showToast({ title: toastText.specChanged, icon: 'none', duration: 1200 })
      return
    }
    addToCart(check.dish)
  }

  const reorderAll = () => {
    let added = 0
    let skippedUnavailable = 0
    let skippedSpec = 0
    lastOrderItems.value.forEach(item => {
      const check = validateHistoryReorderItem(item)
      if (!check.dish || check.reason === 'unavailable') {
        skippedUnavailable += 1
        return
      }
      if (check.reason === 'spec_changed') {
        skippedSpec += 1
        return
      }
      addToCart(check.dish)
      added++
    })
    if (added > 0) uni.vibrateShort({ type: 'medium' })
    showHistoryReorderToast({ added, skippedUnavailable, skippedSpec })
  }

  return {
    handleHomeStartOrder,
    handleFeaturedAdd,
    handleHomeReorderItem,
    handleHomeReorderAll,
    reorderItem,
    reorderAll,
  }
}
