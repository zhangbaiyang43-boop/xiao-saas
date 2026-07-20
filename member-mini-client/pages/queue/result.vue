<template>
  <view class="page">
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
  </view>
</template>

<script>
import { ref } from 'vue'
import { getQueueStatus, getQueueTickets } from '@/api/queue'

export default {
  setup() {
    const tenantId = ref('1')
    const ticketId = ref('')
    const ticket = ref({})
    const queueStatus = ref({})
    const aheadCount = ref(0)

    const unwrap = (res) => {
      if (res?.success === false) throw new Error(res.message || '加载失败')
      return res?.data || res
    }
    const statusText = (status) => ({ waiting: '等待中', called: '已叫号', seated: '已入座', skipped: '已过号' }[status] || '等待中')

    const load = async () => {
      try {
        const local = uni.getStorageSync('queue_ticket')
        if (local) ticket.value = JSON.parse(local) || {}
        const [statusRes, listRes] = await Promise.all([
          getQueueStatus({ tenant_id: tenantId.value }),
          getQueueTickets({ tenant_id: tenantId.value })
        ])
        queueStatus.value = unwrap(statusRes) || {}
        const list = unwrap(listRes) || []
        const current = list.find(item => String(item.id) === String(ticketId.value || ticket.value.id))
        if (current) {
          ticket.value = current
          uni.setStorageSync('queue_ticket', JSON.stringify(current))
        }
        aheadCount.value = list.filter(item => item.queue_type === ticket.value.queue_type && ['waiting', 'called'].includes(item.status) && Number(item.id) !== Number(ticket.value.id)).length
      } catch (err) {
        uni.showToast({ title: err.message || '加载失败', icon: 'none' })
      }
    }

    const goStatus = () => uni.redirectTo({ url: `/pages/queue/index?id=${ticket.value.id || ''}` })

    return { tenantId, ticketId, ticket, queueStatus, aheadCount, statusText, load, goStatus }
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
</style>