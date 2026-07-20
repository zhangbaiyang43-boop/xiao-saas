<template>
  <view class="page">
    <view v-if="loading" class="loading">
      <view class="loading-spinner"></view>
      <text class="loading-text">加载中...</text>
    </view>

    <view v-else-if="error" class="error-state">
      <view class="error-icon">⚠️</view>
      <text class="error-title">{{ error }}</text>
      <button class="refresh-btn" @click="loadDetail">重试</button>
    </view>

    <view v-else-if="consumption" class="detail-container">
      <view class="header-card">
        <view class="amount-section">
          <text class="currency">¥</text>
          <text class="amount">{{ formatMoney(consumption.amount) }}</text>
        </view>
        <text class="product-name">{{ consumption.product_name || consumption.project || '消费' }}</text>
        <text class="status-text">消费成功</text>
      </view>

      <view class="info-section">
        <view class="info-item">
          <text class="info-label">消费门店</text>
          <text class="info-value">{{ consumption.tenant_name || '' }}</text>
        </view>
        <view class="info-item">
          <text class="info-label">消费时间</text>
          <text class="info-value">{{ formatDateTime(consumption.consume_time || consumption.created_at) }}</text>
        </view>
        <view class="info-item" v-if="consumption.points_gained">
          <text class="info-label">获得积分</text>
          <text class="info-value points">+{{ consumption.points_gained }} 积分</text>
        </view>
        <view class="info-item" v-if="consumption.remark">
          <text class="info-label">备注</text>
          <text class="info-value">{{ consumption.remark }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { ref, onMounted } from 'vue'
import { getConsumptionDetail } from '@/api/consumption'
import { formatDateTime, formatMoney } from '@/utils'

export default {
  setup() {
    const loading = ref(true)
    const error = ref('')
    const consumption = ref(null)

    const loadDetail = async () => {
      if (!uni.getStorageSync('customer_token')) {
        error.value = '请先登录'
        loading.value = false
        uni.showToast({ title: '请先登录', icon: 'none' })
        setTimeout(() => {
          uni.reLaunch({ url: '/pages/index/index' })
        }, 1500)
        return
      }

      const pages = getCurrentPages()
      const currentPage = pages[pages.length - 1]
      const options = currentPage.options
      const id = options.id

      if (!id) {
        error.value = '参数错误'
        loading.value = false
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getConsumptionDetail(id)
        if (res.code === 200) {
          consumption.value = res.data
        } else {
          error.value = res.msg || '消费记录加载失败'
          uni.showToast({ title: res.msg || '消费记录加载失败', icon: 'none' })
        }
      } catch (err) {
        error.value = '网络异常，请检查网络连接'
        uni.showToast({ title: '网络异常，请检查网络连接', icon: 'none' })
      } finally {
        loading.value = false
      }
    }

    const goBack = () => {
      uni.navigateBack()
    }

    onMounted(() => {
      loadDetail()
    })

    return {
      loading,
      error,
      consumption,
      loadDetail,
      goBack,
      formatDateTime,
      formatMoney
    }
  },
  onLoad() {
    this.loadDetail()
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 24rpx;
  background: #f5f7fb;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 200rpx 0;
}

.loading-spinner {
  width: 60rpx;
  height: 60rpx;
  border: 4rpx solid #e5e7eb;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  margin-top: 24rpx;
  font-size: 28rpx;
  color: #6b7280;
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 200rpx 40rpx;
}

.error-icon {
  font-size: 80rpx;
  margin-bottom: 24rpx;
}

.error-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 32rpx;
}

.refresh-btn {
  padding: 20rpx 48rpx;
  background: #2563eb;
  color: #fff;
  font-size: 28rpx;
  border-radius: 12rpx;
}

.detail-container {
  padding-bottom: 40rpx;
}

.header-card {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  border-radius: 20rpx;
  padding: 60rpx 40rpx;
  text-align: center;
  margin-bottom: 24rpx;
}

.amount-section {
  margin-bottom: 20rpx;
}

.currency {
  font-size: 36rpx;
  color: #fff;
  margin-right: 4rpx;
}

.amount {
  font-size: 80rpx;
  font-weight: 700;
  color: #fff;
}

.product-name {
  display: block;
  font-size: 36rpx;
  color: #fff;
  margin-bottom: 12rpx;
}

.status-text {
  display: inline-block;
  padding: 8rpx 24rpx;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 24rpx;
  border-radius: 999rpx;
}

.info-section {
  background: #fff;
  border-radius: 16rpx;
  overflow: hidden;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 32rpx 24rpx;
  border-bottom: 1rpx solid #f3f4f6;
}

.info-item:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 28rpx;
  color: #6b7280;
}

.info-value {
  font-size: 28rpx;
  color: #111827;
  text-align: right;
  max-width: 60%;
}

.info-value.points {
  color: #16a34a;
  font-weight: 600;
}
</style>
