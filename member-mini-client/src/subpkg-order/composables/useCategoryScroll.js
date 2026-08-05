import { ref, nextTick } from 'vue'

// 从 menu.vue 拆出来的分类侧栏滚动同步逻辑——点分类跳转到对应菜品区块、
// 菜品区滚动时侧栏跟着高亮当前分类并把可见区域滚到对应位置。跟 DishList.vue
// 之间通过 activeCategory/scrollTarget 两个 ref 及 active-category-change
// 事件配合，逻辑跟原来在 menu.vue 里的一字未改，只是搬了个位置。
//
// 移动时顺手去掉了两个只声明未使用的死状态：dishScrollTopVal、
// categoryScrollTarget——搬到 menu.vue 的 return 里之后一路没有任何模板或
// 组件读过它们，是更早一轮重构留下的残留。
export function useCategoryScroll({ categories, activeCategory, scrollTarget }) {
  const categoryScrollTop = ref(0)
  const categoryItemHeight = 108
  const categoryVisibleRows = 6
  let categoryVisibleStart = 0
  const syncCategoryVisible = (cat) => {
    const idx = categories.value.indexOf(cat)
    if (idx < 0) return
    const visibleEnd = categoryVisibleStart + categoryVisibleRows - 1
    if (idx >= categoryVisibleStart && idx <= visibleEnd) return
    categoryVisibleStart = Math.max(0, idx - 2)
    categoryScrollTop.value = categoryVisibleStart * categoryItemHeight
  }
  const ignoreScroll = ref(false)

  const switchCategory = (cat) => {
    activeCategory.value = cat
    ignoreScroll.value = true
    setTimeout(() => { ignoreScroll.value = false }, 600)
    const idx = categories.value.indexOf(cat)
    syncCategoryVisible(cat)
    scrollTarget.value = ''
    nextTick(() => { scrollTarget.value = 'cat-sec-' + idx })
  }

  // 滚动时"实时查 DOM 现在滚到哪个分类锚点"这段查询逻辑现在在 DishList.vue 组件内部
  // 自己做（因为要查的 .dish-scroll/#cat-sec-N 节点现在是它自己的模板节点，必须用
  // .in(this) 绑定到组件实例才能可靠查到，不能从页面这一层隔着组件边界去查）。这里
  // 只负责接收子组件查完之后报上来的"当前应该高亮哪个分类"结论，然后跟 switchCategory
  // 点击分类时做的事一样：赋值 + 同步左侧分类栏可见区域。
  const handleActiveCategoryChange = (cat) => {
    activeCategory.value = cat
    syncCategoryVisible(cat)
  }

  return {
    categoryScrollTop,
    ignoreScroll,
    switchCategory,
    handleActiveCategoryChange,
  }
}
