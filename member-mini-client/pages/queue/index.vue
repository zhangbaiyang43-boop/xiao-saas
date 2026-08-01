<template>
  <view class="page">
    <view v-if="loading && !ticket.id" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载</text>
    </view>

    <view v-else-if="error && !ticket.id" class="state-card">
      <text class="state-title">{{ error }}</text>
      <button class="primary-btn" @click="load">重新加载</button>
    </view>

    <view v-else-if="!ticket.id" class="empty-card">
      <text class="empty-title">还没有排位号</text>
      <text class="empty-desc">请先到前台或扫码取号。</text>
      <button class="primary-btn" @click="goTake">去取号</button>
    </view>

    <view v-else>
      <view class="top-card">
        <text class="small-label">我的排位号</text>
        <text class="queue-no">{{ ticket.queue_no }}</text>
        <text class="state-text">{{ stateTip }}</text>
      </view>

      <view class="status-list">
        <view class="status-row">
          <text>当前叫号</text>
          <strong>{{ queueStatus.current_called || '暂无' }}</strong>
        </view>
        <view class="status-row">
          <text>前方还有</text>
          <strong>{{ aheadCount }}桌</strong>
        </view>
        <view class="status-row">
          <text>预计等待</text>
          <strong>{{ estimateMinutes }}分钟</strong>
        </view>
      </view>

      <view class="notice-card">
        <text class="notice-title">请留意前台叫号</text>
        <text class="notice-text">预计时间按每桌5-8分钟估算，仅供参考。</text>
      </view>

      <button class="primary-btn" @click="load">刷新状态</button>
    </view>
  </view>
</template>

<script>
import { computed } from 'vue'
import { useQueueTicket } from '@/utils/queue'

export default {
  setup() {
    const { tenantId, ticketId, ticket, queueStatus, aheadCount, loading, error, load } =
      useQueueTicket({ aheadStatuses: ['waiting'] })

    const estimateMinutes = computed(() => `${aheadCount.value * 5}-${Math.max(aheadCount.value * 8, 5)}`)
    const stateTip = computed(() => {
      if (ticket.value.status === 'called') return '已叫号，请尽快到前台'
      if (ticket.value.status === 'seated') return '已入座'
      if (ticket.value.status === 'skipped') return '已过号，请联系前台'
      return '等待中'
    })

    const goTake = () => uni.navigateTo({ url: `/pages/queue/take?tenant_id=${tenantId.value}` })

    return { tenantId, ticketId, ticket, queueStatus, aheadCount, loading, error, estimateMinutes, stateTip, load, goTake }
  },
  onLoad(options) {
    if (options?.tenant_id) this.tenantId = String(options.tenant_id)
    if (options?.id) this.ticketId = String(options.id)
    this.load()
  },
  onPullDownRefresh() {
    this.load().finally(() => uni.stopPullDownRefresh())
  }
}
</script>

<style lang="scss">
.page { min-height: 100vh; padding: 34rpx 28rpx; background: #f5f6fa; }
.top-card, .status-list, .notice-card, .empty-card, .state-card { background: #fff; border-radius: 24rpx; box-shadow: 0 10rpx 26rpx rgba(15, 23, 42, 0.08); }
.top-card { padding: 44rpx 28rpx; text-align: center; }
.small-label, .queue-no, .state-text, .notice-title, .notice-text, .empty-title, .empty-desc { display: block; }
.small-label { color: #64748b; font-size: 28rpx; }
.queue-no { margin-top: 14rpx; color: #ef4444; font-size: 106rpx; line-height: 1; font-weight: 900; }
.state-text { margin-top: 18rpx; color: #16a34a; font-size: 30rpx; font-weight: 900; }
.status-list { margin-top: 24rpx; padding: 0 28rpx; }
.status-row { height: 100rpx; display: flex; align-items: center; justify-content: space-between; border-bottom: 1rpx solid #eef2f7; }
.status-row:last-child { border-bottom: 0; }
.status-row text { color: #64748b; font-size: 28rpx; }
.status-row strong { color: #111827; font-size: 34rpx; }
.notice-card { margin-top: 24rpx; padding: 30rpx; }
.notice-title { color: #111827; font-size: 32rpx; font-weight: 900; }
.notice-text { margin-top: 10rpx; color: #64748b; font-size: 26rpx; line-height: 1.5; }
.primary-btn { width: 100%; height: 96rpx; margin-top: 28rpx; border-radius: 999rpx; background: #ff3d2e; color: #fff; font-size: 34rpx; font-weight: 900; }
.empty-card { margin-top: 120rpx; padding: 44rpx 32rpx; text-align: center; }
.empty-title { color: #111827; font-size: 38rpx; font-weight: 900; }
.empty-desc { margin-top: 14rpx; color: #64748b; font-size: 28rpx; }

.state-card { margin-top: 120rpx; padding: 44rpx 32rpx; text-align: center; }
.state-title { display: block; color: #111827; font-size: 34rpx; font-weight: 900; }
.spinner {
  width: 64rpx; height: 64rpx; margin: 0 auto 24rpx;
  border: 6rpx solid #fde2df; border-top-color: #ff3d2e; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>