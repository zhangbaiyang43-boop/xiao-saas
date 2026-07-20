<template>
  <view class="page">
    <view class="header">
      <text class="title">我的优惠券</text>
      <text class="desc">付款前打开优惠券，给店员扫码或输入券码。</text>
    </view>

    <view class="tabs">
      <view v-for="tab in tabs" :key="tab.key" :class="['tab', { active: activeTab === tab.key }]" @click="switchTab(tab.key)">
        {{ tab.label }}
      </view>
    </view>

    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载优惠券</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <button class="primary-btn" @click="loadCoupons">刷新重试</button>
    </view>

    <view v-else-if="!coupons.length" class="state-card">
      <text class="state-title">{{ emptyTitle }}</text>
      <text class="state-desc">入会、消费或商家发券后，这里会自动显示。</text>
    </view>

    <view v-else class="coupon-list">
      <view v-for="coupon in coupons" :key="coupon.id" class="coupon" @click="goDetail(coupon.id)">
        <view class="coupon-money">
          <text class="amount">¥{{ couponAmount(coupon) }}</text>
          <text class="condition">{{ couponCondition(coupon) }}</text>
        </view>
        <view class="coupon-info">
          <text class="name">{{ coupon.name || '优惠券' }}</text>
          <text class="date">{{ formatDate(coupon.expire_time || coupon.valid_end_time) }} 到期</text>
          <text class="hint">{{ coupon.status === 'UNUSED' ? '点开后给店员核销' : couponStatusText(coupon.status) }}</text>
        </view>
        <text :class="['status', coupon.status]">{{ couponStatusText(coupon.status) }}</text>
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
        uni.reLaunch({ url: '/pages/index/index' })
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
      couponAmount,
      couponCondition,
      couponStatusText,
      formatDate
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
  padding: 28rpx;
  background: #f5f7fb;
}

.header {
  margin-bottom: 22rpx;
}

.title,
.desc,
.state-title,
.state-desc {
  display: block;
}

.title {
  color: #111827;
  font-size: 42rpx;
  font-weight: 800;
}

.desc {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 26rpx;
}

.tabs {
  display: flex;
  padding: 8rpx;
  margin-bottom: 22rpx;
  background: #fff;
  border-radius: 16rpx;
}

.tab {
  flex: 1;
  height: 70rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  border-radius: 12rpx;
  font-size: 28rpx;
  font-weight: 700;
}

.tab.active {
  background: #2563eb;
  color: #fff;
}

.state-card {
  padding: 70rpx 36rpx;
  background: #fff;
  border-radius: 20rpx;
  text-align: center;
}

.spinner {
  width: 56rpx;
  height: 56rpx;
  margin: 0 auto 22rpx;
  border: 6rpx solid #dbeafe;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.state-title {
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.state-desc {
  margin-top: 12rpx;
  color: #64748b;
  font-size: 26rpx;
  line-height: 1.6;
}

.primary-btn {
  width: 100%;
  height: 90rpx;
  margin-top: 28rpx;
  border-radius: 14rpx;
  background: #2563eb;
  color: #fff;
  font-size: 30rpx;
  font-weight: 700;
}

.coupon-list {
  display: grid;
  gap: 18rpx;
}

.coupon {
  position: relative;
  display: flex;
  overflow: hidden;
  border-radius: 18rpx;
  background: #fff;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.05);
}

.coupon-money {
  width: 210rpx;
  padding: 34rpx 12rpx;
  background: #2563eb;
  color: #fff;
  text-align: center;
}

.amount {
  display: block;
  font-size: 42rpx;
  font-weight: 800;
}

.condition {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
}

.coupon-info {
  flex: 1;
  padding: 30rpx;
  padding-right: 92rpx;
}

.name,
.date,
.hint {
  display: block;
}

.name {
  color: #111827;
  font-size: 30rpx;
  font-weight: 800;
}

.date {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 24rpx;
}

.hint {
  margin-top: 12rpx;
  color: #2563eb;
  font-size: 24rpx;
}

.status {
  position: absolute;
  top: 20rpx;
  right: 20rpx;
  color: #2563eb;
  font-size: 24rpx;
  font-weight: 700;
}

.status.USED,
.status.EXPIRED,
.status.REVOKED {
  color: #94a3b8;
}
</style>
