<template>
  <view class="page">

    <!-- 顶部绿色区 -->
    <view class="page-header">
      <text class="ph-title">我的优惠券</text>
      <text class="ph-desc">付款前出示可用券，让店员扫码或输入短券码。</text>
    </view>

    <!-- Tabs -->
    <view class="tabs">
      <view
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab-item', { active: activeTab === tab.key }]"
        @click="switchTab(tab.key)"
      >{{ tab.label }}</view>
    </view>

    <!-- 加载态 -->
    <view v-if="loading" class="state-wrap">
      <view class="loading-ring"></view>
      <text class="state-text">正在加载优惠券</text>
    </view>

    <!-- 错误态 -->
    <view v-else-if="error" class="state-wrap">
      <text class="state-text">{{ error }}</text>
      <button class="btn-primary state-btn" @click="loadCoupons">刷新重试</button>
    </view>

    <!-- 空态 -->
    <view v-else-if="!coupons.length" class="state-wrap">
      <view class="empty-ticket-icon"><view class="eti-circle"></view></view>
      <text class="state-text">{{ emptyTitle }}</text>
      <text class="state-sub">入会、消费或商家发券后，这里会自动显示。</text>
    </view>

    <!-- 列表 -->
    <view v-else class="coupon-list">
      <view
        v-for="coupon in coupons"
        :key="coupon.id"
        :class="['coupon-card', { inactive: coupon.status !== 'UNUSED' }]"
        @click="goDetail(coupon.id)"
      >
        <view class="cc-left">
          <text class="cc-amount">¥{{ couponAmount(coupon) }}</text>
          <text class="cc-cond">{{ couponCondition(coupon) }}</text>
        </view>
        <view class="cc-body">
          <view class="cc-name-row">
            <text class="cc-name">{{ coupon.name || '优惠券' }}</text>
            <text v-if="isExpiringSoon(coupon)" class="cc-urgent">即将到期</text>
          </view>
          <text class="cc-date">{{ formatDate(coupon.expire_time || coupon.valid_end_time) }} 到期</text>
          <button
            v-if="coupon.status === 'UNUSED'"
            class="btn-use"
            @click.stop="goVerify(coupon.id)"
          >出示给店员</button>
          <text v-else class="cc-status">{{ couponStatusText(coupon.status) }}</text>
        </view>
        <text class="cc-arrow">›</text>
      </view>
    </view>

  </view>
</template>

<script>
import { computed, ref } from 'vue'
import { getCustomerCoupons } from '@/api/coupon'
import { couponStatusText, formatDate, formatMoney } from '@/utils'

export default {
  setup() {
    const activeTab = ref('UNUSED')
    const coupons = ref([])
    const loading = ref(false)
    const error = ref('')
    const tabs = [
      { key: 'UNUSED', label: '可用' },
      { key: 'USED', label: '已用' },
      { key: 'EXPIRED', label: '过期' }
    ]

    const emptyTitle = computed(() => {
      if (activeTab.value === 'USED') return '还没有使用过优惠券'
      if (activeTab.value === 'EXPIRED') return '没有过期优惠券'
      return '暂无可用优惠券'
    })

    const normalizeList = (data, status) => {
      if (Array.isArray(data)) return data
      if (Array.isArray(data?.list)) return data.list
      if (status === 'UNUSED') return data?.available || []
      if (status === 'USED') return data?.used || []
      if (status === 'EXPIRED') return data?.expired || []
      return [...(data?.available || []), ...(data?.used || []), ...(data?.expired || [])]
    }

    const couponAmount = (coupon) => formatMoney(coupon.value ?? coupon.amount ?? coupon.discount_amount ?? 0)
    const couponCondition = (coupon) => {
      const min = Number(coupon.min_amount ?? coupon.threshold_amount ?? 0)
      return min > 0 ? `满 ${formatMoney(min)} 可用` : '无门槛'
    }

    const loadCoupons = async () => {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/mine/mine' })
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getCustomerCoupons(activeTab.value)
        if (res.code === 200) coupons.value = normalizeList(res.data, activeTab.value)
        else error.value = res.msg || '优惠券加载失败'
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const switchTab = (key) => {
      activeTab.value = key
      loadCoupons()
    }

    const goDetail = (id) => uni.navigateTo({ url: `/subpkg-coupon/pages/detail?id=${id}` })
    const goVerify = (id) => uni.navigateTo({ url: `/subpkg-common/pages/verify-qr?coupon_id=${id}` })

    const isExpiringSoon = (coupon) => {
      if (coupon.status !== 'UNUSED') return false
      const exp = coupon.expire_time || coupon.valid_end_time
      if (!exp) return false
      const diff = new Date(exp) - Date.now()
      return diff > 0 && diff < 3 * 24 * 60 * 60 * 1000
    }

    return {
      activeTab,
      coupons,
      loading,
      error,
      tabs,
      emptyTitle,
      loadCoupons,
      switchTab,
      goDetail,
      goVerify,
      couponAmount,
      couponCondition,
      couponStatusText,
      formatDate,
      isExpiringSoon,
    }
  },
  onShow() {
    this.loadCoupons()
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #F7F8FA;
}

/* ── 顶部绿色区 ───────────────────────────── */
.page-header {
  padding: 48rpx 32rpx 40rpx;
  background: #07C160;
}

.ph-title {
  display: block;
  color: #fff;
  font-size: 44rpx;
  font-weight: bold;
  line-height: 1.3;
}

.ph-desc {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.85);
  font-size: 26rpx;
}

/* ── Tabs ────────────────────────────────── */
.tabs {
  display: flex;
  margin: 24rpx 24rpx 0;
  background: #fff;
  border-radius: 24rpx;
  padding: 8rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

.tab-item {
  flex: 1;
  height: 80rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30rpx;
  font-weight: 500;
  color: #666;
  border-radius: 18rpx;
  transition: all 0.2s;
}

.tab-item.active {
  background: #07C160;
  color: #fff;
  font-weight: 600;
}

/* ── 状态区 ──────────────────────────────── */
.state-wrap {
  margin: 48rpx 24rpx 0;
  padding: 64rpx 32rpx;
  background: #fff;
  border-radius: 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

.state-icon {
  font-size: 80rpx;
  line-height: 1;
}

.state-text {
  display: block;
  margin-top: 24rpx;
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
  text-align: center;
}

.state-sub {
  display: block;
  margin-top: 12rpx;
  color: #999;
  font-size: 26rpx;
  text-align: center;
  line-height: 1.6;
}

.state-btn {
  margin-top: 32rpx;
  width: 100%;
}

/* ── 通用按钮 ─────────────────────────────── */
.btn-primary {
  display: block;
  height: 88rpx;
  line-height: 88rpx;
  background: #07C160;
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}

/* 加载环 */
.loading-ring {
  width: 72rpx;
  height: 72rpx;
  border: 6rpx solid #e8e8e8;
  border-top-color: #07C160;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── 优惠券列表 ───────────────────────────── */
.coupon-list {
  padding: 24rpx 24rpx 32rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.coupon-card {
  display: flex;
  align-items: stretch;
  background: #fff;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.06);
}

/* 左侧金额面板 */
.cc-left {
  flex-shrink: 0;
  width: 176rpx;
  background: #07C160;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 28rpx 16rpx;
}

.coupon-card.inactive .cc-left {
  background: #c8c9cc;
}

.cc-amount {
  display: block;
  color: #fff;
  font-size: 48rpx;
  font-weight: bold;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.cc-cond {
  display: block;
  margin-top: 8rpx;
  color: rgba(255, 255, 255, 0.85);
  font-size: 22rpx;
  text-align: center;
}

/* 右侧信息区 */
.cc-body {
  flex: 1;
  padding: 24rpx 20rpx;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.cc-name-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.cc-urgent {
  font-size: 20rpx;
  color: #ef4444;
  background: #fef2f2;
  border-radius: 8rpx;
  padding: 2rpx 10rpx;
  font-weight: 600;
  flex-shrink: 0;
}

.cc-name {
  display: block;
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coupon-card.inactive .cc-name {
  color: #999;
}

.cc-date {
  display: block;
  margin-top: 8rpx;
  color: #999;
  font-size: 24rpx;
}

.btn-use {
  display: block;
  width: auto;
  height: 60rpx;
  line-height: 60rpx;
  margin-top: 16rpx;
  padding: 0 24rpx;
  background: #07C160;
  color: #fff;
  font-size: 26rpx;
  font-weight: 600;
  border-radius: 16rpx;
  border: none;
  text-align: center;

  &::after { border: none; }
}

.cc-status {
  display: block;
  margin-top: 12rpx;
  color: #c8c9cc;
  font-size: 26rpx;
}

.cc-arrow {
  flex-shrink: 0;
  align-self: center;
  padding-right: 20rpx;
  color: #c8c9cc;
  font-size: 40rpx;
}

.coupon-card {
  transition: transform 0.1s;
  &:active { transform: scale(0.98); opacity: 0.85; }
}

.empty-ticket-icon {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: #e8f9f0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 8rpx;
}

.eti-circle {
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  border: 6rpx dashed #07C160;
}
</style>

