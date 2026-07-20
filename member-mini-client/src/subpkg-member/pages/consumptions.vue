﻿﻿﻿<template>
  <view class="page">

    <!-- 顶部绿色区 -->
    <view class="page-header">
      <text class="ph-title">消费记录</text>
      <text class="ph-desc">这里会显示你在门店的消费和核销记录。</text>
    </view>

    <!-- 加载态 -->
    <view v-if="loading" class="state-wrap">
      <view class="loading-ring"></view>
      <text class="state-text">正在加载记录</text>
    </view>

    <!-- 错误态 -->
    <view v-else-if="error" class="state-wrap">
      <text class="state-text">{{ error }}</text>
      <button class="btn-primary state-btn" @click="loadConsumptions">刷新重试</button>
    </view>

    <!-- 空态 -->
    <view v-else-if="!consumptions.length" class="state-wrap">
      <text class="state-icon">🧾</text>
      <text class="state-text">暂无消费记录</text>
      <text class="state-sub">到店消费或核销优惠券后，这里会自动显示。</text>
    </view>

    <!-- 列表 -->
    <view v-else class="record-list">
      <view v-for="item in consumptions" :key="item.id" class="record-card">
        <view class="rc-left">
          <text class="rc-title">{{ item.project || item.product_name || '门店消费' }}</text>
          <text class="rc-time">{{ formatDateTime(item.consume_time || item.created_at) }}</text>
          <text v-if="item.remark" class="rc-remark">{{ item.remark }}</text>
        </view>
        <text class="rc-amount">-¥{{ formatMoney(item.amount) }}</text>
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
        uni.reLaunch({ url: '/pages/mine/mine' })
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

/* ── 消费记录列表 ─────────────────────────── */
.record-list {
  padding: 24rpx 24rpx 32rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.record-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

.rc-left {
  flex: 1;
  min-width: 0;
  margin-right: 24rpx;
}

.rc-title {
  display: block;
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rc-time {
  display: block;
  margin-top: 8rpx;
  color: #999;
  font-size: 24rpx;
}

.rc-remark {
  display: block;
  margin-top: 6rpx;
  color: #666;
  font-size: 24rpx;
}

.rc-amount {
  flex-shrink: 0;
  color: #07C160;
  font-size: 36rpx;
  font-weight: bold;
}
</style>

