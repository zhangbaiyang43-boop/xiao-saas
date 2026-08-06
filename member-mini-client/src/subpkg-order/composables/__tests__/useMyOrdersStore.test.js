import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useMyOrdersStore } from '../useMyOrdersStore.js'
import { cancelOrder } from '@/api/order'

vi.mock('@/api/order', () => ({
  cancelOrder: vi.fn(),
}))

function setup() {
  const state = {
    myOrders: ref([]),
    shopId: ref('shop_1'),
    tableNo: ref('A01'),
    orderId: ref(''),
    orderStatus: ref('pending'),
    showSuccess: ref(false),
    diningParticipantToken: ref('tok_1'),
  }
  const stopStatusPoll = vi.fn()
  const store = useMyOrdersStore({ ...state, stopStatusPoll })
  return { state, stopStatusPoll, store }
}

describe('useMyOrdersStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('saveMyOrders / loadMyOrders', () => {
    it('按店铺+桌号存取本地订单列表', () => {
      const { state, store } = setup()
      state.myOrders.value = [{ id: 'o1', status: 'pending' }]

      store.saveMyOrders()
      state.myOrders.value = []
      store.loadMyOrders()

      expect(state.myOrders.value).toEqual([{ id: 'o1', status: 'pending' }])
    })

    it('不同桌号存的是各自独立的一份，不会串桌', () => {
      const { state, store } = setup()
      state.myOrders.value = [{ id: 'o1' }]
      store.saveMyOrders()

      state.tableNo.value = 'B02'
      state.myOrders.value = []
      store.loadMyOrders()

      expect(state.myOrders.value).toEqual([])
    })

    it('本地没有存过时不报错，也不覆盖当前内存里的数据', () => {
      const { state, store } = setup()
      state.myOrders.value = [{ id: 'existing' }]

      store.loadMyOrders()

      expect(state.myOrders.value).toEqual([{ id: 'existing' }])
    })

    it('本地存储损坏（不是合法 JSON）时不抛出，静默保留原状态', () => {
      const { state, store } = setup()
      uni.setStorageSync('my_orders_shop_1_A01', '{not valid json')

      expect(() => store.loadMyOrders()).not.toThrow()
      expect(state.myOrders.value).toEqual([])
    })
  })

  describe('doCancelOrder', () => {
    it('弹确认框，顾客点了取消（不确认）时不发请求', () => {
      const { store } = setup()
      uni.showModal.mockImplementation((opts) => opts.success({ confirm: false }))

      store.doCancelOrder({ id: 'o1', status: 'pending' })

      expect(cancelOrder).not.toHaveBeenCalled()
    })

    it('确认取消后调用取消接口，把这一单标记为已取消并持久化', async () => {
      const { state, store } = setup()
      uni.showModal.mockImplementation((opts) => opts.success({ confirm: true }))
      cancelOrder.mockResolvedValue({ code: 200 })
      const order = { id: 'o1', status: 'pending' }
      state.myOrders.value = [order]

      store.doCancelOrder(order)
      await vi.waitFor(() => expect(order.status).toBe('cancelled'))

      expect(cancelOrder).toHaveBeenCalledWith('o1', 'tok_1')
      const saved = JSON.parse(uni.getStorageSync('my_orders_shop_1_A01'))
      expect(saved[0].status).toBe('cancelled')
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '订单已取消' })
      )
    })

    it('取消的正是当前正在追踪的那一单时，停止轮询并关掉成功页', async () => {
      const { state, store, stopStatusPoll } = setup()
      uni.showModal.mockImplementation((opts) => opts.success({ confirm: true }))
      cancelOrder.mockResolvedValue({ code: 200 })
      state.orderId.value = 'o1'
      state.showSuccess.value = true
      const order = { id: 'o1', status: 'pending' }

      store.doCancelOrder(order)
      await vi.waitFor(() => expect(order.status).toBe('cancelled'))

      expect(stopStatusPoll).toHaveBeenCalledTimes(1)
      expect(state.orderStatus.value).toBe('cancelled')
      expect(state.showSuccess.value).toBe(false)
    })

    it('取消的不是当前追踪的那一单时，不影响正在展示的订单状态', async () => {
      const { state, store, stopStatusPoll } = setup()
      uni.showModal.mockImplementation((opts) => opts.success({ confirm: true }))
      cancelOrder.mockResolvedValue({ code: 200 })
      state.orderId.value = 'o_current'
      state.orderStatus.value = 'preparing'
      const order = { id: 'o_other', status: 'pending' }

      store.doCancelOrder(order)
      await vi.waitFor(() => expect(order.status).toBe('cancelled'))

      expect(stopStatusPoll).not.toHaveBeenCalled()
      expect(state.orderStatus.value).toBe('preparing')
    })

    it('取消接口失败时提示重试，订单状态不会被误标成已取消', async () => {
      const { store } = setup()
      uni.showModal.mockImplementation((opts) => opts.success({ confirm: true }))
      cancelOrder.mockRejectedValue(new Error('商家已接单'))
      const order = { id: 'o1', status: 'pending' }

      store.doCancelOrder(order)
      await vi.waitFor(() =>
        expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '取消失败，请重试' }))
      )

      expect(order.status).toBe('pending')
    })
  })
})
