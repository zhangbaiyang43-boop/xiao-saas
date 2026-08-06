import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useTableCheckout } from '../useTableCheckout.js'
import { requestTableCheckout } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'

vi.mock('@/api/order', () => ({
  requestTableCheckout: vi.fn(),
}))
vi.mock('@/utils/dining', () => ({
  isDiningIdentityError: vi.fn(() => false),
}))

function setup(overrides = {}) {
  const state = {
    shopId: ref('shop_1'),
    diningParticipantToken: ref('tok_1'),
    diningClientId: ref('client_1'),
    tableSessionId: ref('sess_1'),
    canContinueOrder: ref(true),
    checkoutRequestedAt: ref(''),
    checkoutRequested: ref(false),
    isTableSettled: ref(false),
    tableCheckouting: ref(false),
    showOrders: ref(true),
    showSuccess: ref(true),
    activeTab: ref('card'),
  }
  const defaultCallbacks = {
    ensureDiningSession: vi.fn(() => Promise.resolve(true)),
    persistDiningContext: vi.fn(),
  }
  // overrides 里可能替换掉 state 的某个 ref 或者 defaultCallbacks 里的某个函数——
  // 无论替换的是哪一类，callbacks 都要返回"实际传给 useTableCheckout 的那一份"，
  // 不然断言核对的是从没被组合式函数用过的旧 mock，测出来的是假阳性。
  const callbacks = { ...defaultCallbacks, ...overrides }
  const merged = { ...state, ...callbacks }
  const checkout = useTableCheckout(merged)
  return { state, callbacks, checkout }
}

describe('useTableCheckout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isDiningIdentityError.mockReturnValue(false)
  })

  describe('handleTableContinueOrder', () => {
    it('账单已结束时不能继续加菜，弹提示', async () => {
      const { state, checkout, callbacks } = setup({ canContinueOrder: ref(false) })

      await checkout.handleTableContinueOrder()

      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('已结束') })
      )
      expect(callbacks.ensureDiningSession).not.toHaveBeenCalled()
      expect(state.activeTab.value).toBe('card')
    })

    it('本桌会话丢失时先尝试重建，重建失败则提示重新扫码', async () => {
      const { checkout, callbacks } = setup({
        tableSessionId: ref(''),
        ensureDiningSession: vi.fn(() => Promise.resolve(false)),
      })

      await checkout.handleTableContinueOrder()

      expect(callbacks.ensureDiningSession).toHaveBeenCalledWith(true)
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('重新扫码') })
      )
    })

    it('正常继续加菜：撤销已发出的呼叫服务员请求、同步身份、切回点餐 Tab', async () => {
      const { state, checkout, callbacks } = setup()
      state.checkoutRequestedAt.value = '2026-08-06T10:00:00'
      requestTableCheckout.mockResolvedValue({ code: 200 })

      await checkout.handleTableContinueOrder()

      expect(requestTableCheckout).toHaveBeenCalledWith(
        expect.objectContaining({ requested: false })
      )
      expect(state.checkoutRequestedAt.value).toBe('')
      expect(callbacks.persistDiningContext).toHaveBeenCalledWith({
        dining_session_id: 'sess_1',
        participant_token: 'tok_1',
        client_id: 'client_1',
      })
      expect(state.showOrders.value).toBe(false)
      expect(state.showSuccess.value).toBe(false)
      expect(state.activeTab.value).toBe('order')
    })

    it('之前没有呼叫过服务员时，不会平白发一次撤销请求', async () => {
      const { checkout } = setup()

      await checkout.handleTableContinueOrder()

      expect(requestTableCheckout).not.toHaveBeenCalled()
    })
  })

  describe('performTableCheckout', () => {
    it('呼叫成功时记录呼叫时间、震动、提示已通知服务员', async () => {
      const { state, checkout } = setup()
      requestTableCheckout.mockResolvedValue({ code: 200, data: { checkout_requested_at: '2026-08-06T11:00:00' } })

      await checkout.performTableCheckout()

      expect(state.checkoutRequestedAt.value).toBe('2026-08-06T11:00:00')
      expect(uni.vibrateShort).toHaveBeenCalledWith({ type: 'heavy' })
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('已通知服务员') })
      )
    })

    it('后端返回非 200 时提示失败文案，不当成功处理', async () => {
      const { state, checkout } = setup()
      requestTableCheckout.mockResolvedValue({ code: 400, msg: '本桌暂无可结账订单' })

      await checkout.performTableCheckout()

      expect(state.checkoutRequestedAt.value).toBe('')
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '本桌暂无可结账订单' })
      )
    })

    it('身份不同步导致 409 时，重建身份后自动重试一次并成功', async () => {
      const { checkout, callbacks } = setup()
      const identityError = new Error('409')
      isDiningIdentityError.mockImplementation((err) => err === identityError)
      requestTableCheckout
        .mockRejectedValueOnce(identityError)
        .mockResolvedValueOnce({ code: 200, data: {} })

      await checkout.performTableCheckout()

      expect(callbacks.ensureDiningSession).toHaveBeenCalledWith(true)
      expect(requestTableCheckout).toHaveBeenCalledTimes(2)
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('已通知服务员') })
      )
    })

    it('已经是重试状态时不会再次重建身份，避免死循环', async () => {
      const { checkout, callbacks } = setup()
      const identityError = new Error('409')
      isDiningIdentityError.mockImplementation((err) => err === identityError)
      requestTableCheckout.mockRejectedValue(identityError)

      await checkout.performTableCheckout(true)

      expect(callbacks.ensureDiningSession).not.toHaveBeenCalledWith(true)
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '呼叫失败，请重试' })
      )
    })

    it('不是身份类错误时直接提示失败，不尝试重建身份', async () => {
      const { checkout, callbacks } = setup()
      requestTableCheckout.mockRejectedValue(new Error('network down'))

      await checkout.performTableCheckout()

      expect(callbacks.ensureDiningSession).not.toHaveBeenCalledWith(true)
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: '呼叫失败，请重试' })
      )
    })

    it('本地完全没有参与者身份时，请求前先兜底建一次会话', async () => {
      const { checkout, callbacks } = setup({ diningParticipantToken: ref('') })
      requestTableCheckout.mockResolvedValue({ code: 200, data: {} })

      await checkout.performTableCheckout()

      expect(callbacks.ensureDiningSession).toHaveBeenCalledWith()
    })
  })

  describe('handleTableCheckout', () => {
    it('正在结账中或已经呼叫过时，重复点击无效', async () => {
      const { checkout } = setup({ tableCheckouting: ref(true) })

      await checkout.handleTableCheckout()

      expect(requestTableCheckout).not.toHaveBeenCalled()
    })

    it('本桌已结账时弹提示，不重复发起呼叫', async () => {
      const { checkout } = setup({ isTableSettled: ref(true) })

      await checkout.handleTableCheckout()

      expect(uni.showModal).toHaveBeenCalledWith(
        expect.objectContaining({ title: '本桌已结账' })
      )
      expect(requestTableCheckout).not.toHaveBeenCalled()
    })

    it('缺少桌台账单信息时提示重新加载，不发请求', async () => {
      const { checkout } = setup({ tableSessionId: ref('') })

      await checkout.handleTableCheckout()

      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('重新加载') })
      )
      expect(requestTableCheckout).not.toHaveBeenCalled()
    })

    it('正常呼叫流程会话在过程中标记 tableCheckouting，结束后无论成败都会释放', async () => {
      const { state, checkout } = setup()
      requestTableCheckout.mockResolvedValue({ code: 200, data: {} })

      const promise = checkout.handleTableCheckout()
      expect(state.tableCheckouting.value).toBe(true)
      await promise

      expect(state.tableCheckouting.value).toBe(false)
    })
  })
})
