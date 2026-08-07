import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useMemberAuth } from '../useMemberAuth.js'
import { getMemberProfile, getMembershipGrowth, joinByEntranceCode } from '@/api/auth'
import { saveCustomerSession } from '@/utils/auth'
import { getCustomerCoupons } from '@/api/coupon'

vi.mock('@/api/auth', () => ({
  getMemberProfile: vi.fn(),
  getMembershipGrowth: vi.fn(),
  joinByEntranceCode: vi.fn(),
}))
vi.mock('@/utils/auth', () => ({
  saveCustomerSession: vi.fn(),
}))
vi.mock('@/api/coupon', () => ({
  getCustomerCoupons: vi.fn(),
}))

function setup(overrides = {}) {
  const state = {
    shopId: ref('shop_1'),
    tableNo: ref('8'),
    activeTab: ref('order'),
    isCustomerLoggedIn: ref(false),
    authStateVersion: ref(0),
    availableCoupons: ref([]),
    bannerInfo: ref(null),
    isMember: ref(false),
    memberLoading: ref(false),
    memberAuthorizing: ref(false),
  }
  const defaultCallbacks = {
    wxLogin: vi.fn(() => Promise.resolve('wx_code_1')),
    bindCurrentDiningParticipant: vi.fn(() => Promise.resolve()),
    pickAvatarChar: vi.fn((name) => (name ? name[0] : '客')),
    checkWelcomeCoupon: vi.fn(),
  }
  const callbacks = { ...defaultCallbacks, ...overrides }
  const merged = { ...state, ...callbacks }
  const auth = useMemberAuth(merged)
  return { state, callbacks, auth }
}

describe('useMemberAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    uni.getStorageSync.mockReturnValue('')
  })

  describe('hasCustomerIdentity / refreshCustomerAuthState', () => {
    it('本地既没有 token 也没有 phone 时视为未登录', () => {
      const { auth } = setup()
      expect(auth.hasCustomerIdentity.value).toBe(false)
    })

    it('本地有 customer_token 时视为已登录', () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      const { auth } = setup()
      expect(auth.hasCustomerIdentity.value).toBe(true)
    })

    it('refreshCustomerAuthState 会同步 isCustomerLoggedIn 并触发欢迎券检查', () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_phone' ? '138xxxx' : ''))
      const { state, callbacks, auth } = setup()

      auth.refreshCustomerAuthState()

      expect(state.isCustomerLoggedIn.value).toBe(true)
      expect(state.authStateVersion.value).toBe(1)
      expect(callbacks.checkWelcomeCoupon).toHaveBeenCalledTimes(1)
    })
  })

  describe('loadMemberStatus', () => {
    it('没有 customer_token 时不发请求，清空会员卡信息', async () => {
      const { state, auth } = setup()

      await auth.loadMemberStatus()

      expect(getMemberProfile).not.toHaveBeenCalled()
      expect(state.bannerInfo.value).toBe(null)
      expect(state.isMember.value).toBe(false)
    })

    it('已经在加载中时直接跳过，避免并发重复请求', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      const { state, auth } = setup()
      state.memberLoading.value = true

      await auth.loadMemberStatus()

      expect(getMemberProfile).not.toHaveBeenCalled()
    })

    it('拉取成功且有会员标识时，isMember 为 true 并填好 bannerInfo', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      getMemberProfile.mockResolvedValue({
        code: 200,
        data: {
          name: '张三', membership_level: '黄金会员', store_member_no: 8,
          level: '黄金会员', points: 120,
        },
      })
      getCustomerCoupons.mockResolvedValue({ data: [{ id: 'c1' }, { id: 'c2' }] })
      getMembershipGrowth.mockResolvedValue({
        code: 200,
        data: {
          yearly_consumption: 300,
          next_level: { threshold: 1000 },
          level_code: 'LV2',
          levels: [
            { code: 'LV1', point_multiplier: 1 },
            { code: 'LV2', point_multiplier: 1.2 },
          ],
        },
      })
      const { state, auth } = setup()

      await auth.loadMemberStatus()

      expect(state.isMember.value).toBe(true)
      expect(state.availableCoupons.value).toHaveLength(2)
      expect(state.bannerInfo.value).toMatchObject({
        memberNo: '000008',
        levelLabel: '黄金会员',
        levelCode: 'LV2',
        couponCount: 2,
        points: 120,
        pointMultiplier: 1.2,
        growth: 300,
        nextGrowth: 1000,
        nextUpgradeAmount: 700,
      })
      expect(state.memberLoading.value).toBe(false)
    })

    it('growthRes 带 levels 时按当前 level_code 写入 pointMultiplier', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      getMemberProfile.mockResolvedValue({
        code: 200,
        data: { name: '李四', is_member: true, level_code: 'LV3', level: '金卡会员' },
      })
      getCustomerCoupons.mockResolvedValue({ data: [] })
      getMembershipGrowth.mockResolvedValue({
        code: 200,
        data: {
          level_code: 'LV3',
          levels: [
            { code: 'LV1', point_multiplier: 1 },
            { code: 'LV3', point_multiplier: 1.5 },
          ],
        },
      })
      const { state, auth } = setup()

      await auth.loadMemberStatus()

      expect(state.bannerInfo.value.pointMultiplier).toBe(1.5)
    })

    it('growthRes 没有 levels 时 pointMultiplier 退回 1', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      getMemberProfile.mockResolvedValue({ code: 200, data: { name: '王五', is_member: true } })
      getCustomerCoupons.mockResolvedValue({ data: [] })
      getMembershipGrowth.mockResolvedValue({ code: 200, data: { level_code: 'LV1' } })
      const { state, auth } = setup()

      await auth.loadMemberStatus()

      expect(state.bannerInfo.value.pointMultiplier).toBe(1)
    })

    it('拉取成功但没有任何会员标识时，isMember 为 false', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      getMemberProfile.mockResolvedValue({ code: 200, data: { name: '游客' } })
      getCustomerCoupons.mockResolvedValue({ data: [] })
      getMembershipGrowth.mockResolvedValue(null)
      const { state, auth } = setup()

      await auth.loadMemberStatus()

      expect(state.isMember.value).toBe(false)
    })

    it('网络请求失败时不抛出，仅记录错误并复位 loading', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      getMemberProfile.mockRejectedValue(new Error('network down'))
      getCustomerCoupons.mockResolvedValue({ data: [] })
      getMembershipGrowth.mockResolvedValue(null)
      const { state, auth } = setup()

      await expect(auth.loadMemberStatus()).resolves.toBeUndefined()

      expect(state.memberLoading.value).toBe(false)
    })
  })

  describe('switchToCard', () => {
    it('切换到会员卡 tab，若已登录且还没有 bannerInfo 会补拉一次资料', async () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      getMemberProfile.mockResolvedValue({ code: 200, data: { name: '张三', is_member: true } })
      getCustomerCoupons.mockResolvedValue({ data: [] })
      getMembershipGrowth.mockResolvedValue(null)
      const { state, auth } = setup()

      auth.switchToCard()
      await Promise.resolve()
      await Promise.resolve()

      expect(state.activeTab.value).toBe('card')
      expect(getMemberProfile).toHaveBeenCalledTimes(1)
    })

    it('已经有 bannerInfo 时不重复拉取', () => {
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_1' : ''))
      const { state, auth } = setup()
      state.bannerInfo.value = { nameChar: '张' }

      auth.switchToCard()

      expect(getMemberProfile).not.toHaveBeenCalled()
    })
  })

  describe('handleMemberCardAuth', () => {
    it('已经在授权中时直接返回，不重复发起', async () => {
      const { state, auth } = setup()
      state.memberAuthorizing.value = true

      await auth.handleMemberCardAuth({ detail: { code: 'phone_code_1' } })

      expect(joinByEntranceCode).not.toHaveBeenCalled()
    })

    it('拿不到手机号授权 code 时提示重试，不发请求', async () => {
      const { auth } = setup()

      await auth.handleMemberCardAuth({ detail: {} })

      expect(uni.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringContaining('未完成授权') })
      )
      expect(joinByEntranceCode).not.toHaveBeenCalled()
    })

    it('入会成功时保存会话、绑定拼桌身份、刷新会员资料并切到会员卡', async () => {
      joinByEntranceCode.mockResolvedValue({ code: 200, data: { customer_token: 'tok_new' } })
      getMemberProfile.mockResolvedValue({ code: 200, data: { name: '张三', is_member: true } })
      getCustomerCoupons.mockResolvedValue({ data: [] })
      getMembershipGrowth.mockResolvedValue(null)
      uni.getStorageSync.mockImplementation((key) => (key === 'customer_token' ? 'tok_new' : ''))
      const { state, callbacks, auth } = setup()

      await auth.handleMemberCardAuth({ detail: { code: 'phone_code_1' } })

      expect(callbacks.wxLogin).toHaveBeenCalledTimes(1)
      expect(joinByEntranceCode).toHaveBeenCalledWith(
        expect.objectContaining({ phone_code: 'phone_code_1' }),
        expect.objectContaining({ authRedirect: false })
      )
      expect(uni.removeStorageSync).toHaveBeenCalledWith('invite_code')
      expect(saveCustomerSession).toHaveBeenCalledWith({ customer_token: 'tok_new' })
      expect(callbacks.bindCurrentDiningParticipant).toHaveBeenCalledTimes(1)
      expect(state.activeTab.value).toBe('card')
      expect(callbacks.checkWelcomeCoupon).toHaveBeenCalled()
      expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '已登录' }))
      expect(state.memberAuthorizing.value).toBe(false)
    })

    it('入会接口返回非 200 时提示失败，不保存会话', async () => {
      joinByEntranceCode.mockResolvedValue({ code: 400, msg: '邀请码已失效' })
      const { callbacks, auth } = setup()

      await auth.handleMemberCardAuth({ detail: { code: 'phone_code_1' } })

      expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '邀请码已失效' }))
      expect(saveCustomerSession).not.toHaveBeenCalled()
      expect(callbacks.bindCurrentDiningParticipant).not.toHaveBeenCalled()
    })

    it('wxLogin 抛出异常时提示错误信息并复位 authorizing', async () => {
      const { state, auth } = setup({ wxLogin: vi.fn(() => Promise.reject(new Error('用户取消授权'))) })

      await auth.handleMemberCardAuth({ detail: { code: 'phone_code_1' } })

      expect(uni.showToast).toHaveBeenCalledWith(expect.objectContaining({ title: '用户取消授权' }))
      expect(state.memberAuthorizing.value).toBe(false)
    })
  })
})
