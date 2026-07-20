<template>
  <view class="page">
    <view class="top-bg"></view>

    <view v-if="showCouponModal" class="modal-mask" @click="closeCouponModal">
      <view class="modal-card coupon-modal-card" @click.stop>
        <button class="modal-close" @click="closeCouponModal">×</button>
        <text class="modal-title">领取成功</text>
        <text class="modal-desc">付款前打开优惠券，给店员看核销码。</text>
        <view class="gift-amount-card">
          <text class="gift-tag">新人优惠券</text>
          <view class="gift-main">
            <text class="gift-yuan">¥</text>
            <text class="gift-amount">{{ welcomeCouponAmount }}</text>
          </view>
          <text class="gift-rule">{{ welcomeCouponText }}</text>
          <text class="gift-name">{{ welcomeCoupon.name || '优惠券' }}</text>
        </view>
        <button class="primary-btn dark" @click="closeCouponModal">领取优惠券</button>
      </view>
    </view>

    <view v-if="showRuleModal" class="modal-mask" @click="closeRules">
      <view class="modal-card rules-card" @click.stop>
        <button class="modal-close" @click="closeRules">×</button>
        <text class="modal-title">优惠券规则</text>
        <text class="rule-line">1. 付款前先打开优惠券，再出示核销码。</text>
        <text class="rule-line">2. 每张券只能用一次，核销后不能重复使用。</text>
        <text class="rule-line">3. 优惠券以页面显示的门槛和有效期为准。</text>
        <text class="rule-line">4. 如有疑问，请让店员帮你确认。</text>
        <button class="primary-btn dark" @click="closeRules">我知道了</button>
      </view>
    </view>

    <view v-if="isLoading && loggedIn" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载会员信息</text>
      <text class="state-desc">请稍等一下</text>
    </view>

    <view v-else-if="!loggedIn" class="guest-page">
      <view class="guest-card">
        <text class="guest-title">欢迎来到会员中心</text>
        <text class="guest-desc">扫码入会后，可以查看优惠券、出示核销码和消费记录。</text>
        <button class="primary-btn" @click="goEntry">扫码入会领券</button>
        <text class="guest-tip">如果已经扫码，请下拉刷新页面</text>
      </view>
    </view>

    <view v-else>
      <view class="member-card">
        <view class="member-main">
          <view>
            <text class="store-name">{{ tenant_name || '门店会员' }}</text>
            <text class="member-name">{{ customer.name || '会员' }}</text>
            <text class="member-phone">{{ formatPhone(customer.phone) }}</text>
          </view>
        </view>
        <text class="member-tip">先选优惠券，再出示核销码给店员扫码</text>
        <button class="rule-link" @click="openRules">规则</button>
      </view>

      <view class="section coupon-section">
        <view class="section-header">
          <text class="section-title">最近优惠券</text>
          <text class="section-more" @click="goCoupons">全部</text>
        </view>

        <view v-if="recentCoupons.length" class="featured-coupon" @click="goCouponDetail(recentCoupons[0].id)">
          <view class="featured-money">
            <text class="featured-amount">¥{{ couponAmount(recentCoupons[0]) }}</text>
            <text class="featured-condition">{{ couponCondition(recentCoupons[0]) }}</text>
          </view>
          <view class="featured-info">
            <text class="featured-name">{{ recentCoupons[0].name || '优惠券' }}</text>
            <text class="featured-date">{{ formatDate(recentCoupons[0].expire_time || recentCoupons[0].valid_end_time) }} 到期</text>
            <text class="featured-tip">点击后出示核销码</text>
          </view>
          <view class="featured-btn">立即用</view>
        </view>

        <view v-else class="empty-box">
          <text class="empty-title">暂无可用优惠券</text>
          <text class="empty-desc">入会、消费或商家发券后，这里会显示可用券。</text>
        </view>
      </view>

      <view class="primary-actions">
        <view class="big-action verify" @click="goFirstCouponVerify">
          <text class="action-title">出示核销码</text>
          <text class="action-desc">{{ recentCoupons.length ? '使用当前优惠券' : '先选择可用优惠券' }}</text>
        </view>
        <view class="big-action invite" @click="go('/subpkg-member/pages/invite')">
          <text class="action-title">邀请朋友领券</text>
          <text class="action-desc">朋友到店用券后，你可以获得奖励</text>
        </view>
      </view>

      <view class="quick-grid">
        <view class="small-action" @click="goCoupons">
          <text class="small-title">我的优惠券</text>
        </view>
        <view class="small-action" @click="go('/subpkg-member/pages/consumptions')">
          <text class="small-title">消费记录</text>
        </view>
        <view class="small-action" @click="go('/subpkg-member/pages/consumptions')">
          <text class="small-title">最近消费</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { getMemberProfile } from '@/api/auth'
import { getCustomerCoupons } from '@/api/coupon'
import { getMemberConsumptions } from '@/api/consumption'
import { hasCustomerToken } from '@/utils/auth'
import { formatDate, formatMoney, formatPhone } from '@/utils'
import '@/utils/route'

export default {
  setup() {
    const loggedIn = ref(false)
    const isLoading = ref(false)
    const customer = ref({})
    const coupons = ref([])
    const consumptions = ref([])
    const tenant_name = ref(uni.getStorageSync('tenant_name') || '')
    const showCouponModal = ref(false)
    const showRuleModal = ref(false)
    const welcomeCoupon = ref({})

    const recentCoupons = computed(() => coupons.value.filter((item) => item.status === 'UNUSED').slice(0, 3))
    const welcomeCouponText = computed(() => {
      const amount = formatMoney(welcomeCoupon.value.value || welcomeCoupon.value.amount || welcomeCoupon.value.discount_amount || 0)
      const min = Number(welcomeCoupon.value.min_amount || welcomeCoupon.value.threshold_amount || 0)
      return min > 0 ? `满 ${formatMoney(min)} 减 ${amount}` : `无门槛减 ${amount}`
    })
    const welcomeCouponAmount = computed(() => formatMoney(welcomeCoupon.value.value || welcomeCoupon.value.amount || welcomeCoupon.value.discount_amount || 0))

    const couponAmount = (coupon) => formatMoney(coupon.value ?? coupon.amount ?? coupon.discount_amount ?? 0)
    const couponCondition = (coupon) => {
      const min = Number(coupon.min_amount ?? coupon.threshold_amount ?? 0)
      return min > 0 ? `满 ${formatMoney(min)} 可用` : '无门槛'
    }

    const normalizeList = (data) => {
      if (Array.isArray(data)) return data
      if (Array.isArray(data?.list)) return data.list
      return [...(data?.available || []), ...(data?.used || []), ...(data?.expired || [])]
    }

    const loadProfile = async () => {
      if (!hasCustomerToken()) {
        loggedIn.value = false
        isLoading.value = false
        return
      }

      loggedIn.value = true
      isLoading.value = true

      try {
        const [profileRes, couponRes, consumptionRes] = await Promise.all([
          getMemberProfile(),
          getCustomerCoupons('UNUSED'),
          getMemberConsumptions()
        ])

        if (profileRes.code === 200) customer.value = profileRes.data || {}
        else throw new Error(profileRes.msg || '会员信息加载失败')

        coupons.value = couponRes.code === 200 ? normalizeList(couponRes.data) : []
        consumptions.value = consumptionRes.code === 200 ? normalizeList(consumptionRes.data) : []

        const isNew = uni.getStorageSync('is_new_customer') === 'true'
        const hasShown = uni.getStorageSync('coupon_modal_shown') === 'true'
        const storedCoupon = uni.getStorageSync('welcome_coupon')
        if (storedCoupon) {
          try {
            welcomeCoupon.value = JSON.parse(storedCoupon) || {}
          } catch (e) {
            welcomeCoupon.value = {}
          }
        }
        if ((isNew || storedCoupon) && !hasShown) showCouponModal.value = true
      } catch (err) {
        uni.showToast({ title: err.message || '加载失败，请下拉刷新', icon: 'none' })
      } finally {
        isLoading.value = false
      }
    }

    const closeCouponModal = () => {
      showCouponModal.value = false
      uni.setStorageSync('coupon_modal_shown', 'true')
    }
    const openRules = () => {
      showRuleModal.value = true
    }
    const closeRules = () => {
      showRuleModal.value = false
    }

    const go = (url) => uni.navigateTo({ url })
    const goCoupons = () => {
      closeCouponModal()
      uni.navigateTo({ url: '/subpkg-coupon/pages/list' })
    }
    const goCouponDetail = (id) => uni.navigateTo({ url: `/subpkg-coupon/pages/detail?id=${id}` })
    const goFirstCouponVerify = () => {
      const first = recentCoupons.value[0]
      if (!first?.id) {
        uni.showToast({ title: '请先选择一张可用优惠券', icon: 'none' })
        uni.navigateTo({ url: '/subpkg-coupon/pages/list' })
        return
      }
      uni.navigateTo({ url: `/subpkg-common/pages/verify-qr?coupon_id=${first.id}` })
    }
    const goEntry = () => {
      uni.scanCode({
        scanType: ['qrCode'],
        success: (res) => {
          const result = res.result || ''
          let scene = ''
          if (result.startsWith('http')) {
            const match = result.match(/[?&]scene=([^&]+)/)
            scene = match ? decodeURIComponent(match[1]).trim() : ''
          } else {
            scene = result.trim()
          }

          if (!scene) {
            uni.showToast({ title: '没有识别到入口码，请重新扫码', icon: 'none' })
            return
          }

          uni.setStorageSync('entrance_scene', scene)
          uni.navigateTo({ url: `/pages/entry/index?scene=${encodeURIComponent(scene)}` })
        },
        fail: () => {
          uni.showToast({ title: '扫码取消或失败，请再试一次', icon: 'none' })
        }
      })
    }

    return {
      loggedIn,
      isLoading,
      customer,
      coupons,
      consumptions,
      tenant_name,
      showCouponModal,
      showRuleModal,
      welcomeCoupon,
      welcomeCouponText,
      welcomeCouponAmount,
      recentCoupons,
      couponAmount,
      couponCondition,
      loadProfile,
      closeCouponModal,
      openRules,
      closeRules,
      go,
      goCoupons,
      goCouponDetail,
      goFirstCouponVerify,
      goEntry,
      formatDate,
      formatMoney,
      formatPhone
    }
  },
  onLoad(options) {
    if (options?.scene) {
      uni.setStorageSync('entrance_scene', options.scene)
      uni.redirectTo({ url: `/pages/entry/index?scene=${encodeURIComponent(options.scene)}` })
    }
  },
  onShow() {
    this.loadProfile()
  },
  onPullDownRefresh() {
    this.loadProfile().finally(() => {
      uni.stopPullDownRefresh()
    })
  }
}
</script>

<style lang="scss">
.page {
  position: relative;
  min-height: 100vh;
  padding: 28rpx;
  padding-bottom: 120rpx;
  background: #12c76a;
}

.top-bg {
  position: fixed;
  inset: 0 0 auto 0;
  height: 520rpx;
  background:
    radial-gradient(circle at 16% 18%, rgba(255, 241, 118, 0.58), transparent 170rpx),
    radial-gradient(circle at 88% 12%, rgba(255, 255, 255, 0.28), transparent 190rpx),
    linear-gradient(180deg, #10c969 0%, #0bbf62 100%);
  pointer-events: none;
}

.page > view:not(.top-bg):not(.modal-mask) {
  position: relative;
  z-index: 1;
}

.guest-page {
  padding-top: 120rpx;
}

.guest-card,
.state-card,
.member-card,
.section,
.modal-card,
.small-action {
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 12rpx 30rpx rgba(6, 95, 70, 0.16);
}

.guest-card {
  padding: 44rpx 36rpx;
  text-align: center;
}

.guest-title {
  display: block;
  color: #111827;
  font-size: 42rpx;
  font-weight: 900;
}

.guest-desc {
  display: block;
  margin-top: 18rpx;
  color: #64748b;
  font-size: 28rpx;
  line-height: 1.6;
}

.guest-tip {
  display: block;
  margin-top: 20rpx;
  color: #94a3b8;
  font-size: 24rpx;
}

.primary-btn,
.plain-btn {
  width: 100%;
  height: 94rpx;
  border-radius: 999rpx;
  font-size: 32rpx;
  font-weight: 900;
}

.primary-btn {
  margin-top: 34rpx;
  background: #ff3d2e;
  color: #fff;
}

.plain-btn {
  margin-top: 16rpx;
  background: #f1f5f9;
  color: #334155;
}

.state-card {
  margin-top: 120rpx;
  padding: 64rpx 36rpx;
  text-align: center;
}

.spinner {
  width: 56rpx;
  height: 56rpx;
  margin: 0 auto;
  border: 6rpx solid #dcfce7;
  border-top-color: #16a34a;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.state-title,
.state-desc {
  display: block;
}

.state-title {
  margin-top: 24rpx;
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.state-desc {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 26rpx;
}

.member-card {
  position: relative;
  padding: 36rpx;
  min-height: 230rpx;
  overflow: hidden;
  color: #202124;
  background: linear-gradient(135deg, #fff66b 0%, #fff8bb 58%, #ffffff 100%);
  border: 4rpx solid rgba(255, 255, 255, 0.72);
}

.member-card::after {
  content: "";
  position: absolute;
  right: -64rpx;
  top: -74rpx;
  width: 220rpx;
  height: 220rpx;
  border-radius: 50%;
  background: rgba(16, 185, 129, 0.16);
}

.member-main {
  position: relative;
  z-index: 1;
}

.store-name,
.member-name,
.member-phone,
.member-tip {
  display: block;
}

.store-name {
  color: #15803d;
  font-size: 26rpx;
  font-weight: 700;
}

.member-name {
  margin-top: 18rpx;
  color: #111827;
  font-size: 48rpx;
  font-weight: 900;
}

.member-phone {
  margin-top: 8rpx;
  color: #475569;
  font-size: 26rpx;
}

.member-tip {
  position: relative;
  z-index: 1;
  margin-top: 34rpx;
  padding-right: 110rpx;
  color: #374151;
  font-size: 26rpx;
}

.rule-link {
  position: absolute;
  right: 28rpx;
  bottom: 26rpx;
  z-index: 2;
  width: 88rpx;
  height: 52rpx;
  padding: 0;
  border-radius: 999rpx;
  background: #ff4d2d;
  color: #fff;
  font-size: 24rpx;
  font-weight: 900;
  line-height: 52rpx;
}

.section {
  margin-top: 24rpx;
  padding: 28rpx;
}

.coupon-section {
  border: 4rpx solid #fff1a8;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20rpx;
}

.section-title {
  color: #111827;
  font-size: 34rpx;
  font-weight: 900;
}

.section-more {
  color: #15803d;
  font-size: 26rpx;
  font-weight: 800;
}

.featured-coupon {
  position: relative;
  display: flex;
  overflow: hidden;
  min-height: 164rpx;
  border-radius: 20rpx;
  background: #fff7ed;
  border: 3rpx solid #fed7aa;
}

.featured-money {
  width: 210rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #ff3d2e 0%, #ef1f1f 100%);
  color: #fff;
  text-align: center;
}

.featured-amount {
  font-size: 52rpx;
  font-weight: 900;
}

.featured-condition {
  margin-top: 8rpx;
  font-size: 22rpx;
}

.featured-info {
  flex: 1;
  padding: 28rpx 130rpx 28rpx 28rpx;
}

.featured-name,
.featured-date,
.featured-tip {
  display: block;
}

.featured-name {
  color: #111827;
  font-size: 34rpx;
  font-weight: 900;
}

.featured-date {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 24rpx;
}

.featured-tip {
  margin-top: 12rpx;
  color: #ef4444;
  font-size: 24rpx;
  font-weight: 800;
}

.featured-btn {
  position: absolute;
  right: 22rpx;
  top: 50%;
  transform: translateY(-50%);
  padding: 14rpx 22rpx;
  border-radius: 999rpx;
  background: #ffdf35;
  color: #7c2d12;
  font-size: 24rpx;
  font-weight: 900;
}

.primary-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18rpx;
  margin-top: 22rpx;
}

.big-action {
  min-height: 160rpx;
  padding: 28rpx;
  border-radius: 24rpx;
  color: #fff;
  box-shadow: 0 12rpx 28rpx rgba(6, 95, 70, 0.18);
}

.big-action.verify {
  background: linear-gradient(135deg, #ff4d2d 0%, #ef1f1f 100%);
}

.big-action.invite {
  background: linear-gradient(135deg, #ffbf1f 0%, #ff8a00 100%);
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16rpx;
  margin-top: 22rpx;
}

.small-action {
  min-height: 104rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18rpx 12rpx;
  text-align: center;
}

.action-title,
.action-desc,
.small-title {
  display: block;
}

.action-title {
  color: inherit;
  font-size: 34rpx;
  font-weight: 900;
}

.action-desc {
  margin-top: 8rpx;
  color: rgba(255, 255, 255, 0.9);
  font-size: 24rpx;
  line-height: 1.35;
}

.small-title {
  color: #111827;
  font-size: 30rpx;
  font-weight: 900;
}

.empty-box {
  padding: 42rpx 28rpx;
  border-radius: 16rpx;
  background: #f8fafc;
}

.empty-title,
.empty-desc {
  display: block;
}

.empty-title {
  color: #111827;
  font-size: 28rpx;
  font-weight: 800;
}

.empty-desc {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 24rpx;
  line-height: 1.6;
}

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48rpx;
  background: rgba(15, 23, 42, 0.48);
}

.modal-card {
  position: relative;
  width: 100%;
  padding: 42rpx 34rpx;
  text-align: center;
}

.modal-title {
  display: block;
  color: #111827;
  font-size: 38rpx;
  font-weight: 900;
}

.modal-desc {
  display: block;
  margin-top: 18rpx;
  color: #64748b;
  font-size: 28rpx;
  line-height: 1.6;
}

.modal-close {
  position: absolute;
  top: 22rpx;
  right: 24rpx;
  width: 56rpx;
  height: 56rpx;
  padding: 0;
  border-radius: 50%;
  background: transparent;
  color: #94a3b8;
  font-size: 44rpx;
  line-height: 56rpx;
}

.rules-card {
  text-align: left;
}

.rules-card .modal-title {
  text-align: center;
}

.rule-line {
  display: block;
  margin-top: 22rpx;
  color: #334155;
  font-size: 28rpx;
  line-height: 1.55;
}

.coupon-modal-card {
  padding-top: 52rpx;
}

.gift-amount-card {
  position: relative;
  margin: 32rpx 0 26rpx;
  padding: 34rpx 28rpx 30rpx;
  border-radius: 24rpx;
  background: linear-gradient(180deg, #fff6a8 0%, #fff9d8 58%, #ffffff 100%);
  border: 4rpx solid #ffe45c;
  text-align: center;
  overflow: hidden;
}

.gift-amount-card::after {
  content: "";
  position: absolute;
  right: -60rpx;
  top: -70rpx;
  width: 190rpx;
  height: 190rpx;
  border-radius: 50%;
  background: rgba(255, 77, 45, 0.12);
}

.gift-main {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: center;
  align-items: baseline;
  color: #ef1f1f;
  line-height: 1;
}

.gift-yuan {
  font-size: 44rpx;
  font-weight: 900;
}

.gift-amount {
  font-size: 118rpx;
  font-weight: 900;
}

.gift-amount-card .gift-rule {
  position: relative;
  z-index: 1;
  display: block;
  margin-top: 8rpx;
  color: #7c2d12;
  font-size: 34rpx;
  font-weight: 900;
}

.gift-amount-card .gift-name {
  position: relative;
  z-index: 1;
  display: block;
  margin-top: 14rpx;
  color: #475569;
  font-size: 26rpx;
  font-weight: 700;
}

.gift-amount-card .gift-tag {
  position: relative;
  z-index: 1;
  display: inline-flex;
  padding: 8rpx 18rpx;
  border-radius: 999rpx;
  background: #ff4d2d;
  color: #fff;
  font-size: 24rpx;
  font-weight: 900;
}

.gift-coupon {
  position: relative;
  display: grid;
  grid-template-columns: 128rpx 1fr;
  align-items: center;
  margin: 34rpx 0 10rpx;
  overflow: hidden;
  border-radius: 14rpx;
  background: #fff7ed;
  text-align: left;
}

.gift-icon {
  height: 128rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 2rpx dashed #fed7aa;
  color: #ef4444;
  font-size: 48rpx;
  font-weight: 900;
}

.gift-info {
  padding: 24rpx 28rpx;
}

.gift-name,
.gift-rule {
  display: block;
}

.gift-name {
  color: #111827;
  font-size: 34rpx;
  font-weight: 900;
}

.gift-rule {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 26rpx;
}

.gift-tag {
  position: absolute;
  top: 0;
  right: 0;
  padding: 8rpx 16rpx;
  border-bottom-left-radius: 12rpx;
  background: #fef3c7;
  color: #92400e;
  font-size: 24rpx;
}

.primary-btn.dark {
  background: #27272a;
}
</style>
