import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useDiningSession } from '../useDiningSession.js'
import { getCurrentDiningOrders } from '@/api/order'
import { bindDiningParticipant } from '@/api/auth'
import { resolveDiningIdentity, isDiningIdentityError } from '@/utils/dining'

vi.mock('@/api/order', () => ({
  getCurrentDiningOrders: vi.fn(),
}))
vi.mock('@/api/auth', () => ({
  bindDiningParticipant: vi.fn(),
}))
vi.mock('@/utils/dining', () => ({
  resolveDiningIdentity: vi.fn(),
  persistDiningContext: vi.fn(),
  isDiningIdentityError: vi.fn(() => false),
}))

// 建一套全新的页面状态 + 组合式函数实例——每条用例互不干扰，且完全对应
// menu.vue 里真实传给 useDiningSession(...) 的那组 ref。
function setup() {
  const state = {
    shopId: ref('shop_1'),
    tableNo: ref('A01'),
    diningSessionId: ref(''),
    diningParticipantToken: ref(''),
    diningClientId: ref(''),
    tableSessionClosed: ref(false),
    tableSessionStatus: ref(''),
    tableSessionTotal: ref(0),
    tableSessionClosedNotice: ref(''),
    checkoutRequestedAt: ref(''),
    tableSessionClosedAt: ref(''),
    myOrders: ref([]),
  }
  const normalizePaymentMode = vi.fn((mode) => mode || 'prepay')
  const saveMyOrders = vi.fn()
  const session = useDiningSession({ ...state, normalizePaymentMode, saveMyOrders })
  return { state, normalizePaymentMode, saveMyOrders, session }
}

describe('useDiningSession', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('ensureDiningSession', () => {
    it('本桌会话已关闭且不是强制重建时，不请求身份接口直接返回 false', async () => {
      const { state, session } = setup()
      state.tableSessionClosed.value = true

      const ok = await session.ensureDiningSession(false)

      expect(ok).toBe(false)
      expect(resolveDiningIdentity).not.toHaveBeenCalled()
    })

    it('身份接口返回 ok 时写入 dining 上下文并把 tableSessionClosed 复位为 false', async () => {
      const { state, session } = setup()
      state.tableSessionClosed.value = true
      resolveDiningIdentity.mockResolvedValue({
        ok: true,
        data: { dining_session_id: 'sess_1', participant_token: 'tok_1', client_id: 'client_1' },
      })

      const ok = await session.ensureDiningSession(true)

      expect(ok).toBe(true)
      expect(state.diningSessionId.value).toBe('sess_1')
      expect(state.diningParticipantToken.value).toBe('tok_1')
      expect(state.diningClientId.value).toBe('client_1')
      expect(state.tableSessionClosed.value).toBe(false)
    })

    it('身份接口返回不 ok 时不动任何本地状态，返回 false', async () => {
      const { state, session } = setup()
      resolveDiningIdentity.mockResolvedValue({ ok: false })

      const ok = await session.ensureDiningSession(true)

      expect(ok).toBe(false)
      expect(state.diningSessionId.value).toBe('')
      expect(state.tableSessionClosed.value).toBe(false)
    })
  })

  describe('syncDiningOrders', () => {
    it('本地身份不全且不是重试时，先强制重建身份再重试一次', async () => {
      const { state, session } = setup()
      // diningSessionId/diningParticipantToken 都是空的，diningOrderQuery() 拿不全
      resolveDiningIdentity.mockResolvedValue({
        ok: true,
        data: { dining_session_id: 'sess_1', participant_token: 'tok_1' },
      })
      getCurrentDiningOrders.mockResolvedValue({ code: 200, data: { orders: [] } })

      const ok = await session.syncDiningOrders(false)

      expect(resolveDiningIdentity).toHaveBeenCalledTimes(1)
      expect(getCurrentDiningOrders).toHaveBeenCalledTimes(1)
      expect(ok).toBe(true)
    })

    it('已经是重试状态、身份仍不全时直接返回 false，不会再递归', async () => {
      const { session } = setup()

      const ok = await session.syncDiningOrders(true)

      expect(ok).toBe(false)
      expect(resolveDiningIdentity).not.toHaveBeenCalled()
      expect(getCurrentDiningOrders).not.toHaveBeenCalled()
    })

    it('后端返回 identity_mismatch 且不是重试时，重建身份后只重试一次', async () => {
      const { state, session } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'
      resolveDiningIdentity.mockResolvedValue({
        ok: true,
        data: { dining_session_id: 'sess_2', participant_token: 'tok_2' },
      })
      getCurrentDiningOrders
        .mockResolvedValueOnce({ code: 200, data: { identity_mismatch: true } })
        .mockResolvedValueOnce({ code: 200, data: { orders: [] } })

      const ok = await session.syncDiningOrders(false)

      expect(ok).toBe(true)
      expect(resolveDiningIdentity).toHaveBeenCalledTimes(1)
      expect(getCurrentDiningOrders).toHaveBeenCalledTimes(2)
    })

    it('抛出的错误被判定为身份类错误时，重建身份后重试一次', async () => {
      const { state, session } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'
      isDiningIdentityError.mockReturnValue(true)
      resolveDiningIdentity.mockResolvedValue({
        ok: true,
        data: { dining_session_id: 'sess_2', participant_token: 'tok_2' },
      })
      getCurrentDiningOrders
        .mockRejectedValueOnce(new Error('409'))
        .mockResolvedValueOnce({ code: 200, data: { orders: [] } })

      const ok = await session.syncDiningOrders(false)

      expect(ok).toBe(true)
      expect(resolveDiningIdentity).toHaveBeenCalledTimes(1)
    })

    it('抛出的错误不是身份类错误时，直接返回 false，不重建身份', async () => {
      const { state, session } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'
      isDiningIdentityError.mockReturnValue(false)
      getCurrentDiningOrders.mockRejectedValue(new Error('network down'))

      const ok = await session.syncDiningOrders(false)

      expect(ok).toBe(false)
      expect(resolveDiningIdentity).not.toHaveBeenCalled()
    })

    it('同步成功时把订单、桌台状态、结账信息都写回页面状态，并调用 saveMyOrders', async () => {
      const { state, session, saveMyOrders } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'
      getCurrentDiningOrders.mockResolvedValue({
        code: 200,
        data: {
          session_status: 'ACTIVE',
          table_total: 88.5,
          checkout_requested_at: '2026-08-06T10:00:00',
          closed_at: '',
          orders: [{ id: 'o1', status: 'pending', items: [], total: 30 }],
        },
      })

      const ok = await session.syncDiningOrders(false)

      expect(ok).toBe(true)
      expect(state.tableSessionStatus.value).toBe('ACTIVE')
      expect(state.tableSessionTotal.value).toBe(88.5)
      expect(state.tableSessionClosed.value).toBe(false)
      expect(state.checkoutRequestedAt.value).toBe('2026-08-06T10:00:00')
      expect(state.myOrders.value).toHaveLength(1)
      expect(state.myOrders.value[0].id).toBe('o1')
      expect(saveMyOrders).toHaveBeenCalledTimes(1)
    })

    it('会话已关闭时清空本地"当前桌台"相关的 storage key 并写提示文案', async () => {
      const { state, session } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'
      uni.setStorageSync('table_no', 'A01')
      uni.setStorageSync('dining_session_id', 'sess_1')
      getCurrentDiningOrders.mockResolvedValue({
        code: 200,
        data: { session_status: 'CLOSED', orders: [] },
      })

      await session.syncDiningOrders(false)

      expect(state.tableSessionClosed.value).toBe(true)
      expect(state.tableSessionClosedNotice.value).toContain('已结束')
      expect(uni.removeStorageSync).toHaveBeenCalledWith('table_no')
      expect(uni.removeStorageSync).toHaveBeenCalledWith('dining_session_id')
      expect(uni.removeStorageSync).toHaveBeenCalledWith('dining_participant_token')
    })

    it('第一次同步到人数不弹提示，后续人数变多才弹提示（避免"自己刚进桌"被误报）', async () => {
      const { state, session } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'

      getCurrentDiningOrders.mockResolvedValue({
        code: 200,
        data: { orders: [], participant_count: 1 },
      })
      await session.syncDiningOrders(false)
      expect(uni.showToast).not.toHaveBeenCalled()

      getCurrentDiningOrders.mockResolvedValue({
        code: 200,
        data: { orders: [], participant_count: 2 },
      })
      await session.syncDiningOrders(false)
      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('加入') })
      )
    })

    it('人数没有变多时（相同或减少）不弹提示', async () => {
      const { state, session } = setup()
      state.diningSessionId.value = 'sess_1'
      state.diningParticipantToken.value = 'tok_1'

      getCurrentDiningOrders.mockResolvedValue({
        code: 200,
        data: { orders: [], participant_count: 2 },
      })
      await session.syncDiningOrders(false)
      await session.syncDiningOrders(false)

      expect(uni.showToast).not.toHaveBeenCalled()
    })
  })

  describe('bindCurrentDiningParticipant', () => {
    it('没有 participant_token 时不发请求', async () => {
      const { session } = setup()

      await session.bindCurrentDiningParticipant()

      expect(bindDiningParticipant).not.toHaveBeenCalled()
    })

    it('有 participant_token 时带正确参数发请求', async () => {
      const { state, session } = setup()
      state.diningParticipantToken.value = 'tok_1'
      bindDiningParticipant.mockResolvedValue({ code: 200 })

      await session.bindCurrentDiningParticipant()

      expect(bindDiningParticipant).toHaveBeenCalledWith(
        { tenant_id: 'shop_1', participant_token: 'tok_1' },
        { authRedirect: false }
      )
    })

    it('请求失败时静默吞掉，不抛出', async () => {
      const { state, session } = setup()
      state.diningParticipantToken.value = 'tok_1'
      bindDiningParticipant.mockRejectedValue(new Error('boom'))

      await expect(session.bindCurrentDiningParticipant()).resolves.toBeUndefined()
    })
  })
})
