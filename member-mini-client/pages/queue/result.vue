<template>
  <view class="page">
    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <button class="primary-btn" @click="load">重新加载</button>
    </view>

    <template v-else>
      <view class="result-card">
        <text class="label">您的排位号</text>
        <text class="queue-no">{{ ticket.queue_no || '-' }}</text>
        <text class="status">{{ statusText(ticket.status) }}</text>
      </view>

      <view class="info-grid">
        <view class="info-card">
          <text class="info-value">{{ ticket.ahead_count ?? aheadCount }}</text>
          <text class="info-label">前方等待桌数</text>
        </view>
        <view class="info-card">
          <text class="info-value">{{ queueStatus.current_called || '暂无' }}</text>
          <text class="info-label">当前叫号</text>
        </view>
      </view>

      <view class="notice-card">
        <text class="notice-title">请留意前台叫号</text>
        <text class="notice-text">过号请重新联系前台。排位信息刷新后仍会保留。</text>
      </view>

      <button class="primary-btn" @click="goStatus">查看排位状态</button>
    </template>
  </view>
</template>

<script>
import { useQueueTicket } from '@/utils/queue'

export default {
  setup() {
    const { tenantId, ticketId, ticket, queueStatus, aheadCount, loading, error, load } =
      useQueueTicket({ aheadStatuses: ['waiting', 'called'] })

    const statusText = (status) => ({ waiting: '等待中', called: '已叫号', seated: '已入座', skipped: '已过号' }[status] || '等待中')

    const goStatus = () => uni.redirectTo({ url: `/pages/queue/index?id=${ticket.value.id || ''}` })

    return { tenantId, ticketId, ticket, queueStatus, aheadCount, loading, error, statusText, load, goStatus }
  },
  onLoad(options) {
    if (options?.tenant_id) this.tenantId = String(options.tenant_id)
    if (options?.id) this.ticketId = String(options.id)
    this.load()
  }
}
</script>

<style lang="scss">
.page { min-height: 100vh; padding: 34rpx 28rpx; background: #f5f6fa; }
.result-card { padding: 48rpx 28rpx; border-radius: 28rpx; background: #fff; text-align: center; box-shadow: 0 10rpx 26rpx rgba(15, 23, 42, 0.08); }
.label, .queue-no, .status, .info-value, .info-label, .notice-title, .notice-text { display: block; }
.label { color: #64748b; font-size: 28rpx; }
.queue-no { margin-top: 14rpx; color: #ef4444; font-size: 112rpx; line-height: 1; font-weight: 900; }
.status { margin-top: 18rpx; color: #16a34a; font-size: 30rpx; font-weight: 900; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18rpx; margin-top: 24rpx; }
.info-card, .notice-card { background: #fff; border-radius: 22rpx; box-shadow: 0 8rpx 20rpx rgba(15, 23, 42, 0.06); }
.info-card { padding: 30rpx 16rpx; text-align: center; }
.info-value { color: #111827; font-size: 46rpx; font-weight: 900; }
.info-label { margin-top: 8rpx; color: #64748b; font-size: 24rpx; }
.notice-card { margin-top: 24rpx; padding: 30rpx; }
.notice-title { color: #111827; font-size: 32rpx; font-weight: 900; }
.notice-text { margin-top: 10rpx; color: #64748b; font-size: 26rpx; line-height: 1.5; }
.primary-btn { width: 100%; height: 96rpx; margin-top: 28rpx; border-radius: 999rpx; background: #ff3d2e; color: #fff; font-size: 34rpx; font-weight: 900; }

.state-card { margin-top: 120rpx; padding: 44rpx 32rpx; text-align: center; background: #fff; border-radius: 24rpx; box-shadow: 0 10rpx 26rpx rgba(15, 23, 42, 0.08); }
.state-title { display: block; color: #111827; font-size: 34rpx; font-weight: 900; }
.spinner {
  width: 64rpx; height: 64rpx; margin: 0 auto 24rpx;
  border: 6rpx solid #fde2df; border-top-color: #ff3d2e; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>