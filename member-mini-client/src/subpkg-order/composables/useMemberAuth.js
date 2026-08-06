import { computed } from 'vue'
import { getMemberProfile, getMembershipGrowth, joinByEntranceCode } from '@/api/auth'
import { saveCustomerSession } from '@/utils/auth'
import { getCustomerCoupons } from '@/api/coupon'
import { reportError } from '@/utils/monitor'

// 从 menu.vue 拆出来的"会员登录 + 拉会员资料"整条流程——手机号授权登录、
// 登录后刷新会员卡片数据、判断"当前算不算有会员身份"。之所以是 MEDIUM 而不是
// LOW：这几个函数会真的发网络请求、写本地存储（customer_token 由
// saveCustomerSession 写入）、改动好几个跨功能共享的页面状态（
// isCustomerLoggedIn、availableCoupons、activeTab），不是纯展示计算。
//
// bindCurrentDiningParticipant/wxLogin/pickAvatarChar/checkWelcomeCoupon 都
// 通过参数传入而不是这里重新实现：前者是"拼桌身份"这条高风险链路自己的方法，
// 后两个分别是别的组合式函数/模块级工具函数，这里只是复用。
export function useMemberAuth({
  shopId, tableNo, activeTab, isCustomerLoggedIn, authStateVersion, availableCoupons,
  bannerInfo, isMember, memberLoading, memberAuthorizing,
  wxLogin, bindCurrentDiningParticipant, pickAvatarChar, checkWelcomeCoupon,
}) {
  const refreshCustomerAuthState = () => {
    authStateVersion.value += 1
    isCustomerLoggedIn.value = Boolean(uni.getStorageSync('customer_token') || uni.getStorageSync('customer_phone'))
    checkWelcomeCoupon()
  }
  const hasCustomerIdentity = computed(() => {
    authStateVersion.value
    return Boolean(uni.getStorageSync('customer_token') || uni.getStorageSync('customer_phone'))
  })

  const loadMemberStatus = async (opts = {}) => {
    refreshCustomerAuthState()
    const token = uni.getStorageSync('customer_token')
    isCustomerLoggedIn.value = Boolean(token || uni.getStorageSync('customer_phone'))
    if (!token) {
      bannerInfo.value = null
      isMember.value = false
      return
    }
    if (memberLoading.value) return
    memberLoading.value = true
    try {
      const [profileRes, couponRes, growthRes] = await Promise.all([
        getMemberProfile({ authRedirect: opts.authRedirect !== false }),
        getCustomerCoupons('UNUSED', { authRedirect: opts.authRedirect !== false }).catch(() => null),
        getMembershipGrowth().catch(() => null),
      ])
      if (profileRes?.code === 200 && profileRes?.data) {
        const p = profileRes.data
        const g = growthRes?.code === 200 ? (growthRes.data || {}) : {}
        isMember.value = !!(p.membership_level || p.is_member || p.member_card || p.membership_expire_at || p.level)
        const coupons = Array.isArray(couponRes?.data) ? couponRes.data : []
        availableCoupons.value = coupons
        bannerInfo.value = {
          nameChar: pickAvatarChar(p.name),
          avatar: p.avatar || p.avatar_url || p.headimgurl || '',
          memberNo: p.store_member_no ? String(p.store_member_no).padStart(6, '0') : '',
          levelLabel: p.level || p.membership_level || '普通会员',
          levelCode: p.level_code || g.level_code || 'LV1',
          couponCount: coupons.length,
          coupons,
          points: Number(p.points || 0),
          // 这三个字段之前从未被 /v1/member/profile 填过，进度条永远不渲染，
          // 现在改从与 growth.vue 同一个 /v1/member/membership 取数，避免两处
          // 各算一套对不上号。
          growth: Number(g.yearly_consumption || 0),
          nextGrowth: Number(g.next_level?.threshold || 0),
          nextUpgradeAmount: Math.max(0, Number(g.next_level?.threshold || 0) - Number(g.yearly_consumption || 0)),
        }
      }
    } catch (e) {
      // 会员卡资料拉取失败时顾客只会看到一张空白/不完整的会员卡，自己不知道
      // 是网络问题还是账号问题——这里之前是彻底静默的，加上上报才能看见
      // "拉资料失败率"，不用等顾客投诉"我的会员卡怎么是空的"才知道。
      reportError('member_auth.load_status', e)
    }
    finally { memberLoading.value = false }
  }

  const switchToCard = () => {
    activeTab.value = 'card'
    refreshCustomerAuthState()
    if (hasCustomerIdentity.value && !bannerInfo.value) loadMemberStatus({ authRedirect: false })
  }

  const handleMemberCardAuth = async (event) => {
    if (memberAuthorizing.value) return
    const phoneCode = event?.detail?.code || event?.detail?.phoneCode || ''
    if (!phoneCode) return uni.showToast({ title: '未完成授权，请重试', icon: 'none' })
    memberAuthorizing.value = true
    try {
      const code = await wxLogin()
      const res = await joinByEntranceCode({
        scene: uni.getStorageSync('entrance_scene') || '',
        tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
        table_no: tableNo.value || uni.getStorageSync('table_no') || '',
        code,
        phone_code: phoneCode,
        agreement_accepted: true,
        invite_code: uni.getStorageSync('invite_code') || '',
      }, { authRedirect: false })
      if (res?.code !== 200) {
        uni.showToast({ title: res?.msg || '加入会员失败，请重试', icon: 'none' })
        return
      }
      // 邀请码用过就清掉，避免以后在别的店误用
      uni.removeStorageSync('invite_code')
      saveCustomerSession(res.data || {})
      await bindCurrentDiningParticipant()
      await loadMemberStatus({ authRedirect: false })
      activeTab.value = 'card'
      uni.showToast({ title: '已登录', icon: 'none' })
      checkWelcomeCoupon()
    } catch (err) {
      uni.showToast({ title: err?.message || '授权未完成，请重试', icon: 'none' })
    } finally {
      memberAuthorizing.value = false
    }
  }

  return {
    refreshCustomerAuthState,
    hasCustomerIdentity,
    loadMemberStatus,
    switchToCard,
    handleMemberCardAuth,
  }
}
