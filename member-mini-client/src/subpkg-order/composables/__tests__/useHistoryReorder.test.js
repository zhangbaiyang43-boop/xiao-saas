import { describe, expect, it, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { useHistoryReorder } from '../useHistoryReorder.js'

describe('useHistoryReorder home start-order feedback', () => {
  beforeEach(() => {
    uni.showToast.mockClear()
  })

  it('toasts 门店休息中 and does not switch tab when the shop is closed', () => {
    const activeTab = ref('home')
    const { handleHomeStartOrder } = useHistoryReorder({
      activeTab,
      storeClosed: ref(true),
      canStartOrdering: ref(false),
      canHomeAdd: ref(false),
      featuredDish: ref(null),
      validateHistoryReorderItem: vi.fn(),
      homeLastOrderItems: ref([]),
      lastOrderItems: ref([]),
      hasSpecs: vi.fn(),
      addToCart: vi.fn(),
      openSpecSheet: vi.fn(),
    })
    handleHomeStartOrder()
    expect(activeTab.value).toBe('home')
    expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '门店休息中' }))
  })

  it('toasts 暂无菜品 when the menu is empty', () => {
    const activeTab = ref('home')
    const { handleHomeStartOrder } = useHistoryReorder({
      activeTab,
      storeClosed: ref(false),
      canStartOrdering: ref(false),
      canHomeAdd: ref(false),
      featuredDish: ref(null),
      validateHistoryReorderItem: vi.fn(),
      homeLastOrderItems: ref([]),
      lastOrderItems: ref([]),
      hasSpecs: vi.fn(),
      addToCart: vi.fn(),
      openSpecSheet: vi.fn(),
    })
    handleHomeStartOrder()
    expect(activeTab.value).toBe('home')
    expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '暂无菜品' }))
  })

  it('switches to the order tab when ordering is allowed', () => {
    const activeTab = ref('home')
    const { handleHomeStartOrder } = useHistoryReorder({
      activeTab,
      storeClosed: ref(false),
      canStartOrdering: ref(true),
      canHomeAdd: ref(true),
      featuredDish: ref({ id: 'd1' }),
      validateHistoryReorderItem: vi.fn(),
      homeLastOrderItems: ref([]),
      lastOrderItems: ref([]),
      hasSpecs: vi.fn(),
      addToCart: vi.fn(),
      openSpecSheet: vi.fn(),
    })
    handleHomeStartOrder()
    expect(activeTab.value).toBe('order')
    expect(uni.showToast).not.toHaveBeenCalled()
  })

  it('toasts when featured add is blocked because the shop is closed', () => {
    const addToCart = vi.fn()
    const { handleFeaturedAdd } = useHistoryReorder({
      activeTab: ref('home'),
      storeClosed: ref(true),
      canStartOrdering: ref(false),
      canHomeAdd: ref(false),
      featuredDish: ref({ id: 'd1' }),
      validateHistoryReorderItem: vi.fn(),
      homeLastOrderItems: ref([]),
      lastOrderItems: ref([]),
      hasSpecs: vi.fn(),
      addToCart,
      openSpecSheet: vi.fn(),
    })
    handleFeaturedAdd()
    expect(addToCart).not.toHaveBeenCalled()
    expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '门店休息中' }))
  })
})
