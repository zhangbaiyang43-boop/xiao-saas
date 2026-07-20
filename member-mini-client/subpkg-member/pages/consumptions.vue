<template>
  <view class="page">
    <view class="header">
      <text class="title">消费记录</text>
      <text class="desc">这里会显示你在门店的消费和核销记录。</text>
    </view>

    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载记录</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <button class="primary-btn" @click="loadConsumptions">刷新重试</button>
    </view>

    <view v-else-if="!consumptions.length" class="state-card">
      <text class="state-title">暂无消费记录</text>
      <text class="state-desc">到店消费或核销优惠券后，这里会自动显示。</text>
    </view>

    <view v-else class="record-list">
      <view v-for="item in consumptions" :key="item.id" class="record-item">
        <view>
          <text class="record-title">{{ item.project || item.product_name || '门店消费' }}</text>
          <text class="record-time">{{ formatDateTime(item.consume_time || item.created_at) }}</text>
          <text v-if="item.remark" class="record-remark">{{ item.remark }}</text>
        </view>
        <text class="record-money">¥{{ formatMoney(item.amount) }}</text>
      </view>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getMemberConsumptions } from '@/api/consumption'
import { formatDateTime, formatMoney } from '@/utils'

export default {
  setup() {
    const loading = ref(false)
    const error = ref('')
    const consumptions = ref([])

    const normalizeList = (data) => {
      if (Array.isArray(data)) return data
      if (Array.isArray(data?.list)) return data.list
      return []
    }

    const loadConsumptions = async () => {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/index/index' })
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getMemberConsumptions()
        if (res.code === 200) consumptions.value = normalizeList(res.data)
        else error.value = res.msg || '消费记录加载失败'
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    return { loading, error, consumptions, loadConsumptions, formatDateTime, formatMoney }
  },
  onShow() {
    this.loadConsumptions()
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
  margin-bottom: 24rpx;
}

.title,
.desc,
.state-title,
.state-desc,
.record-title,
.record-time,
.record-remark {
  display: block;
}

.title {
  color: #111827;
  font-size: 42rpx;
  font-weight: 900;
}

.desc {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 26rpx;
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

.record-list {
  display: grid;
  gap: 18rpx;
}

.record-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 30rpx;
  background: #fff;
  border-radius: 18rpx;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.05);
}

.record-title {
  color: #111827;
  font-size: 30rpx;
  font-weight: 800;
}

.record-time {
  margin-top: 8rpx;
  color: #94a3b8;
  font-size: 24rpx;
}

.record-remark {
  margin-top: 8rpx;
  color: #64748b;
  font-size: 24rpx;
}

.record-money {
  color: #dc2626;
  font-size: 32rpx;
  font-weight: 900;
}
</style>
