<template>
  <view class="page">
    <view v-if="loading" class="card center">
      <view class="spinner"></view>
      <text>正在加载邀请数据</text>
    </view>

    <view v-else class="content">
      <view class="hero card">
        <text class="title">我的邀请</text>
        <text class="desc">分享给朋友，朋友到店用券后，你可以获得奖励。</text>
        <view class="stats">
          <view>
            <text class="num">{{ summary.invited_count || 0 }}</text>
            <text class="label">已邀请</text>
          </view>
          <view>
            <text class="num">¥{{ money(summary.pending_commission) }}</text>
            <text class="label">待结算</text>
          </view>
          <view>
            <text class="num">¥{{ money(summary.settled_commission) }}</text>
            <text class="label">已结算</text>
          </view>
        </view>
      </view>

      <view class="card invite-card">
        <text class="card-title">邀请方式</text>
        <view class="code-box">
          <text class="code-label">我的邀请码</text>
          <text class="code">{{ summary.invite_code || '-' }}</text>
        </view>
        <button class="primary-btn" open-type="share">邀请好友入会</button>
        <text class="tip">好友通过你的邀请进入小程序，入会后到店核销，系统才会产生奖励。</text>
      </view>

      <view class="card">
        <view class="section-head">
          <text class="card-title">奖励记录</text>
          <text class="refresh" @click="loadData">刷新</text>
        </view>
        <view v-if="records.length === 0" class="empty">
          <text>暂无奖励记录</text>
          <text>朋友用券后会显示在这里。</text>
        </view>
        <view v-for="item in records" :key="item.id" class="record">
          <view>
            <text class="record-title">{{ item.level === 1 ? '一级奖励' : '二级奖励' }}</text>
            <text class="record-desc">朋友消费约 ¥{{ money(item.amount) }}</text>
          </view>
          <view class="record-money">
            <text>¥{{ money(item.commission_amount) }}</text>
            <text>{{ item.status === 'SETTLED' ? '已结算' : '待结算' }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getCommissionRecords, getInviteSummary } from '@/api/invite'

export default {
  setup() {
    const loading = ref(false)
    const summary = ref({})
    const records = ref([])

    const money = (value) => Number(value || 0).toFixed(2).replace(/\.00$/, '')

    const loadData = async () => {
      loading.value = true
      try {
        const [summaryRes, recordRes] = await Promise.all([
          getInviteSummary(),
          getCommissionRecords()
        ])
        if (summaryRes.code === 200) summary.value = summaryRes.data || {}
        if (recordRes.code === 200) records.value = recordRes.data?.items || []
      } catch (error) {
        uni.showToast({ title: '邀请数据加载失败', icon: 'none' })
      } finally {
        loading.value = false
      }
    }

    return { loading, summary, records, money, loadData }
  },
  onShow() {
    this.loadData()
  },
  onShareAppMessage() {
    const tenantId = this.summary.tenant_id || uni.getStorageSync('tenant_id') || ''
    const inviteCode = this.summary.invite_code || ''
    return {
      title: this.summary.share_title || '扫码成为会员，领优惠券',
      path: `/pages/entry/index?tenant_id=${encodeURIComponent(tenantId)}&invite_code=${encodeURIComponent(inviteCode)}`
    }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 28rpx;
  background: #f5f7fb;
}

.card {
  padding: 30rpx;
  margin-bottom: 22rpx;
  background: #fff;
  border-radius: 20rpx;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.05);
}

.center {
  margin-top: 120rpx;
  text-align: center;
}

.spinner {
  width: 56rpx;
  height: 56rpx;
  margin: 0 auto 20rpx;
  border: 6rpx solid #dbeafe;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.hero {
  background: #1f2937;
  color: #fff;
}

.title,
.desc,
.num,
.label,
.card-title,
.tip,
.code-label,
.code,
.record-title,
.record-desc {
  display: block;
}

.title {
  font-size: 42rpx;
  font-weight: 800;
}

.desc {
  margin-top: 14rpx;
  color: #cbd5e1;
  font-size: 26rpx;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14rpx;
  margin-top: 34rpx;
}

.stats view {
  padding: 20rpx 10rpx;
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.12);
  text-align: center;
}

.num {
  font-size: 34rpx;
  font-weight: 800;
}

.label {
  margin-top: 8rpx;
  color: #cbd5e1;
  font-size: 22rpx;
}

.card-title {
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.code-box {
  margin: 24rpx 0;
  padding: 28rpx;
  border-radius: 16rpx;
  background: #f8fafc;
  text-align: center;
}

.code-label {
  color: #64748b;
  font-size: 24rpx;
}

.code {
  margin-top: 12rpx;
  color: #111827;
  font-size: 42rpx;
  font-weight: 800;
}

.primary-btn {
  width: 100%;
  height: 94rpx;
  border-radius: 14rpx;
  background: #2563eb;
  color: #fff;
  font-size: 32rpx;
  font-weight: 700;
}

.tip {
  margin-top: 18rpx;
  color: #64748b;
  font-size: 24rpx;
  line-height: 1.6;
}

.section-head,
.record {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.refresh {
  color: #2563eb;
  font-size: 26rpx;
}

.empty {
  padding: 40rpx 0;
  color: #94a3b8;
  text-align: center;
}

.empty text {
  display: block;
  margin-top: 8rpx;
}

.record {
  padding: 24rpx 0;
  border-bottom: 1rpx solid #edf2f7;
}

.record:last-child {
  border-bottom: 0;
}

.record-title {
  color: #111827;
  font-size: 28rpx;
  font-weight: 700;
}

.record-desc {
  margin-top: 6rpx;
  color: #64748b;
  font-size: 24rpx;
}

.record-money {
  text-align: right;
}

.record-money text {
  display: block;
  color: #dc2626;
  font-weight: 800;
}

.record-money text:last-child {
  margin-top: 6rpx;
  color: #64748b;
  font-size: 22rpx;
  font-weight: 400;
}
</style>
