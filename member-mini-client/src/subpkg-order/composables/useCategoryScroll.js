import { ref, nextTick, watch } from 'vue'
import { categoryAnchorId } from './useDishCategories.js'

// 分类侧栏与右侧菜品区块联动：点击用稳定锚点 scroll-into-view；
// 程序滚动期间 scroll-spy 不得覆盖用户点中的分类。
export function useCategoryScroll({ categories, activeCategory, scrollTarget }) {
  const categoryScrollTop = ref(0)
  const categoryItemHeight = 108
  const categoryVisibleRows = 6
  let categoryVisibleStart = 0
  const programmaticCategory = ref('')
  const ignoreScroll = ref(false)

  const syncCategoryVisible = (cat) => {
    const idx = categories.value.indexOf(cat)
    if (idx < 0) return
    const visibleEnd = categoryVisibleStart + categoryVisibleRows - 1
    if (idx >= categoryVisibleStart && idx <= visibleEnd) return
    categoryVisibleStart = Math.max(0, idx - 2)
    categoryScrollTop.value = categoryVisibleStart * categoryItemHeight
  }

  const retargetScroll = (cat) => {
    if (!cat) {
      scrollTarget.value = ''
      return
    }
    const id = categoryAnchorId(cat)
    scrollTarget.value = ''
    nextTick(() => {
      scrollTarget.value = id
    })
  }

  const switchCategory = (cat) => {
    activeCategory.value = cat
    programmaticCategory.value = cat
    ignoreScroll.value = true
    syncCategoryVisible(cat)
    retargetScroll(cat)
  }

  // Spy 在程序滚动期间只接受「已经滚到用户点的那一类」；其它分类一律丢掉。
  const handleActiveCategoryChange = (cat) => {
    if (programmaticCategory.value) {
      if (cat !== programmaticCategory.value) return
      programmaticCategory.value = ''
      ignoreScroll.value = false
      scrollTarget.value = ''
      syncCategoryVisible(cat)
      return
    }
    activeCategory.value = cat
    syncCategoryVisible(cat)
  }

  const handleProgrammaticScrollSettled = (cat) => {
    if (!programmaticCategory.value) return
    if (cat !== programmaticCategory.value) return
    programmaticCategory.value = ''
    ignoreScroll.value = false
    scrollTarget.value = ''
    syncCategoryVisible(cat)
  }

  watch(categories, (next, prev) => {
    const list = Array.isArray(next) ? next : []
    const prevList = Array.isArray(prev) ? prev : []
    const sameOrder = list.length === prevList.length && list.every((c, i) => c === prevList[i])
    const current = activeCategory.value
    if (current && list.includes(current)) {
      if (sameOrder) return
      programmaticCategory.value = current
      ignoreScroll.value = true
      syncCategoryVisible(current)
      retargetScroll(current)
      return
    }
    const fallback = list[0] || ''
    activeCategory.value = fallback
    if (!fallback) {
      programmaticCategory.value = ''
      ignoreScroll.value = false
      scrollTarget.value = ''
      return
    }
    programmaticCategory.value = fallback
    ignoreScroll.value = true
    syncCategoryVisible(fallback)
    retargetScroll(fallback)
  })

  return {
    categoryScrollTop,
    ignoreScroll,
    switchCategory,
    handleActiveCategoryChange,
    handleProgrammaticScrollSettled,
  }
}
