import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { useCategoryScroll } from '../useCategoryScroll.js'
import { categoryAnchorId, useDishCategories } from '../useDishCategories.js'

const menuSource = readFileSync(
  fileURLToPath(new URL('../../pages/menu.vue', import.meta.url)),
  'utf8',
)
const dishListSource = readFileSync(
  fileURLToPath(new URL('../../components/DishList.vue', import.meta.url)),
  'utf8',
)

function setup(initialCategories = ['推荐', '烧烤', '川菜']) {
  const categories = ref(initialCategories)
  const activeCategory = ref('')
  const scrollTarget = ref('')
  const api = useCategoryScroll({ categories, activeCategory, scrollTarget })
  return { categories, activeCategory, scrollTarget, ...api }
}

describe('P0 menu category sync', () => {
  it('CASE 1: clicking a category sets a stable id, not an array index', async () => {
    const { activeCategory, scrollTarget, switchCategory } = setup()
    switchCategory('川菜')
    expect(activeCategory.value).toBe('川菜')
    expect(scrollTarget.value).toBe('')
    await nextTick()
    const expected = categoryAnchorId('川菜')
    expect(scrollTarget.value).toBe(expected)
    expect(expected.startsWith('cat-sec-')).toBe(true)
    expect(/^cat-sec-\d+$/.test(expected)).toBe(false)
    expect(scrollTarget.value).not.toBe('cat-sec-2')
    expect(scrollTarget.value).not.toBe('cat-sec-0')
  })

  it('CASE 2: spy cannot overwrite the clicked category during programmatic scroll', async () => {
    const { activeCategory, switchCategory, handleActiveCategoryChange } = setup()
    switchCategory('川菜')
    await nextTick()
    handleActiveCategoryChange('烧烤')
    expect(activeCategory.value).toBe('川菜')
    handleActiveCategoryChange('推荐')
    expect(activeCategory.value).toBe('川菜')
  })

  it('CASE 3: delayed category_order keeps the user-selected category and retargets by name', async () => {
    const { categories, activeCategory, scrollTarget, switchCategory } = setup(['烧烤', '川菜'])
    switchCategory('川菜')
    await nextTick()
    expect(activeCategory.value).toBe('川菜')
    const idBefore = scrollTarget.value
    expect(idBefore).toBe(categoryAnchorId('川菜'))

    categories.value = ['川菜', '烧烤', '火锅']
    await nextTick()
    expect(activeCategory.value).toBe('川菜')
    await nextTick()
    expect(scrollTarget.value).toBe(categoryAnchorId('川菜'))
    expect(scrollTarget.value).toBe(idBefore)
  })

  it('CASE 4: reordering categories keeps the same section id and dish grouping', () => {
    const allDishes = ref([
      { id: 1, name: '宫保鸡丁', category: '川菜', tags: [] },
      { id: 2, name: '烤串', category: '烧烤', tags: [] },
      { id: 3, name: '火锅底料', category: '火锅', tags: [] },
    ])
    const categoryOrder = ref(['烧烤', '火锅', '川菜'])
    const specCartItems = ref([])
    const first = useDishCategories({
      allDishes,
      categoryOrder,
      specCartItems,
      hasSpecs: () => false,
    })
    expect(first.categories.value).toEqual(['烧烤', '火锅', '川菜'])
    const chuanId = categoryAnchorId('川菜')
    expect(first.dishesByCategory('川菜').map(d => d.name)).toEqual(['宫保鸡丁'])

    categoryOrder.value = ['川菜', '烧烤', '火锅']
    expect(first.categories.value).toEqual(['川菜', '烧烤', '火锅'])
    expect(categoryAnchorId('川菜')).toBe(chuanId)
    expect(first.dishesByCategory('川菜').map(d => d.name)).toEqual(['宫保鸡丁'])
    expect(first.dishesByCategory('烧烤').map(d => d.name)).toEqual(['烤串'])
  })

  it('settling on the clicked category releases the spy lock', async () => {
    const {
      activeCategory,
      scrollTarget,
      switchCategory,
      handleProgrammaticScrollSettled,
      handleActiveCategoryChange,
    } = setup()
    switchCategory('川菜')
    await nextTick()
    handleProgrammaticScrollSettled('川菜')
    expect(activeCategory.value).toBe('川菜')
    expect(scrollTarget.value).toBe('')
    handleActiveCategoryChange('烧烤')
    expect(activeCategory.value).toBe('烧烤')
  })

  it('keeps a WeChat-legal id and does not default-overwrite user choice in menu.vue', () => {
    const id = categoryAnchorId('川菜')
    expect(/^[A-Za-z][A-Za-z0-9_-]*$/.test(id)).toBe(true)
    expect(id).not.toMatch(/[^A-Za-z0-9_-]/)

    expect(menuSource).toContain('applyDefaultCategoryIfNeeded')
    expect(menuSource).toContain('handleProgrammaticScrollSettled')
    expect(menuSource.match(/activeCategory\.value = categories\.value\[0\]/g)).toHaveLength(1)
    expect(dishListSource).toContain('categoryAnchorId(cat)')
    expect(dishListSource).not.toContain('cat-sec-${catIdx}')
    expect(dishListSource).not.toContain("'#cat-sec-' + i")
    expect(dishListSource).toContain('this.scrollTarget || this.ignoreScroll')
  })
})
