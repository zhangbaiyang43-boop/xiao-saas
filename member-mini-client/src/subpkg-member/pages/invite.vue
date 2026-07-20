<template>
  <view class="page">

    <!-- 加载态 -->
    <view v-if="loading" class="state-wrap">
      <view class="loading-ring"></view>
      <text class="state-text">正在加载邀请数据</text>
    </view>

    <view v-else class="content">

      <!-- 顶部英雄卡 -->
      <view class="hero-card">
        <text class="hc-title">邀请朋友到店，双方得奖励</text>
        <text class="hc-desc">{{ summary.inviter_reward_text || '邀请朋友到店用券，朋友首次到店后，你们都能获得奖励。' }}</text>
        <view class="stats-row">
          <view class="stat-item">
            <text class="stat-num">{{ summary.invited_count || 0 }}</text>
            <text class="stat-label">已邀请</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-num">{{ summary.visited_count || 0 }}</text>
            <text class="stat-label">已到店</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-num">{{ summary.reward_count || 0 }}</text>
            <text class="stat-label">已奖励</text>
          </view>
          <view class="stat-divider"></view>
          <view class="stat-item">
            <text class="stat-num">{{ summary.pending_count || 0 }}</text>
            <text class="stat-label">待到店</text>
          </view>
        </view>
      </view>

      <!-- 邀请方式卡 -->
      <view class="card invite-card">
        <text class="card-title">邀请好友入会</text>
        <view class="code-box">
          <text class="code-label">我的邀请码</text>
          <text class="code-val">{{ summary.invite_code || '-' }}</text>
        </view>
        <button class="btn-primary" open-type="share">邀请好友入会</button>
        <text class="card-tip">{{ summary.invitee_reward_text || '好友通过你的链接入会，首次到店核销后，双方均可获得奖励。' }}</text>
      </view>

      <!-- 好友记录卡 -->
      <view class="card">
        <view class="card-header">
          <text class="card-title">好友记录</text>
          <text class="refresh-btn" @click="loadData">刷新</text>
        </view>

        <view v-if="records.length === 0" class="empty-wrap">
          <text class="empty-icon">🎁</text>
          <text class="empty-text">暂无好友记录</text>
          <text class="empty-sub">好友通过你的邀请入会后会显示在这里。</text>
        </view>

        <view v-for="item in records" :key="item.invitee_id" class="record-item">
          <view class="ri-left">
            <text class="ri-name">{{ item.invitee_name }}</text>
            <view class="ri-meta-row">
              <text class="ri-meta">加入：{{ item.joined_at || '-' }}</text>
              <text v-if="item.has_visited" class="ri-meta visited-text">到店：{{ item.visited_at || '-' }}</text>
            </view>
          </view>
          <view class="ri-right">
            <view :class="['status-badge', item.has_visited ? 'badge-visited' : 'badge-pending']">
              {{ item.has_visited ? '已到店' : '未到店' }}
            </view>
            <text :class="['ri-reward', item.reward_status === '奖励已发放' ? 'reward-done' : item.has_visited ? 'reward-pending' : 'reward-wait']">
              {{ item.reward_status }}
            </text>
          </view>
        </view>

      </view>

    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getInviteRecords, getInviteSummary } from '@/api/invite'

export default {
  setup() {
    const loading = ref(false)
    const summary = ref({})
    const records = ref([])

    const loadData = async () => {
      loading.value = true
      try {
        const [summaryRes, recordsRes] = await Promise.all([
          getInviteSummary(),
          getInviteRecords()
        ])
        if (summaryRes.code === 200) summary.value = summaryRes.data || {}
        if (recordsRes.code === 200) records.value = Array.isArray(recordsRes.data) ? recordsRes.data : []
      } catch (error) {
        uni.showToast({ title: '邀请数据加载失败', icon: 'none' })
      } finally {
        loading.value = false
      }
    }

    return { loading, summary, records, loadData }
  },
  onShow() {
    this.loadData()
  },
  onShareAppMessage() {
    const tenantId = this.summary.tenant_id || uni.getStorageSync('tenant_id') || ''
    const inviteCode = this.summary.invite_code || ''
    return {
      title: '我送你一张优惠券，到店可用',
      path: `/pages/entry/index?tenant_id=${encodeURIComponent(tenantId)}&invite_code=${encodeURIComponent(inviteCode)}`
    }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #F7F8FA;
}

/* ── 状态区 ──────────────────────────────── */
.state-wrap {
  margin: 120rpx 24rpx 0;
  padding: 64rpx 32rpx;
  background: #fff;
  border-radius: 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.state-text {
  display: block;
  margin-top: 24rpx;
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
}

.loading-ring {
  width: 72rpx;
  height: 72rpx;
  border: 6rpx solid #e8e8e8;
  border-top-color: #07C160;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── 内容区 ──────────────────────────────── */
.content {
  padding-bottom: 32rpx;
}

/* ── 英雄卡 ──────────────────────────────── */
.hero-card {
  padding: 48rpx 32rpx 40rpx;
  background: #07C160;
}

.hc-title {
  display: block;
  color: #fff;
  font-size: 40rpx;
  font-weight: bold;
  line-height: 1.35;
}

.hc-desc {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.88);
  font-size: 26rpx;
  line-height: 1.6;
}

.stats-row {
  display: flex;
  align-items: center;
  margin-top: 32rpx;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 24rpx;
  padding: 24rpx 0;
}

.stat-item {
  flex: 1;
  text-align: center;
}

.stat-num {
  display: block;
  color: #fff;
  font-size: 36rpx;
  font-weight: bold;
  line-height: 1.2;
}

.stat-label {
  display: block;
  margin-top: 8rpx;
  color: rgba(255, 255, 255, 0.8);
  font-size: 24rpx;
}

.stat-divider {
  width: 2rpx;
  height: 56rpx;
  background: rgba(255, 255, 255, 0.3);
}

/* ── 通用卡片 ─────────────────────────────── */
.card {
  margin: 24rpx 24rpx 0;
  padding: 32rpx;
  background: #fff;
  border-radius: 32rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

.card-title {
  display: block;
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24rpx;
}

.refresh-btn {
  color: #07C160;
  font-size: 28rpx;
}

/* ── 邀请码区 ─────────────────────────────── */
.invite-card .card-title {
  margin-bottom: 24rpx;
}

.code-box {
  margin-bottom: 28rpx;
  padding: 28rpx;
  background: #F7F8FA;
  border-radius: 20rpx;
  text-align: center;
}

.code-label {
  display: block;
  color: #999;
  font-size: 24rpx;
}

.code-val {
  display: block;
  margin-top: 12rpx;
  color: #111;
  font-size: 52rpx;
  font-weight: bold;
  letter-spacing: 8rpx;
}

/* ── 通用按钮 ─────────────────────────────── */
.btn-primary {
  display: block;
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  background: #07C160;
  color: #fff;
  font-size: 34rpx;
  font-weight: 600;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}

.card-tip {
  display: block;
  margin-top: 16rpx;
  color: #999;
  font-size: 24rpx;
  line-height: 1.6;
}

/* ── 空态 ────────────────────────────────── */
.empty-wrap {
  padding: 48rpx 0 16rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.empty-icon {
  font-size: 72rpx;
  line-height: 1;
}

.empty-text {
  display: block;
  margin-top: 16rpx;
  color: #333;
  font-size: 30rpx;
  font-weight: 600;
}

.empty-sub {
  display: block;
  margin-top: 8rpx;
  color: #999;
  font-size: 26rpx;
}

/* ── 好友记录 ─────────────────────────────── */
.record-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24rpx 0;
  border-bottom: 2rpx solid #F7F8FA;
}

.record-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.ri-left {
  flex: 1;
  min-width: 0;
}

.ri-name {
  display: block;
  color: #111;
  font-size: 30rpx;
  font-weight: 600;
}

.ri-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
  margin-top: 8rpx;
}

.ri-meta {
  color: #999;
  font-size: 24rpx;
}

.visited-text {
  color: #07C160;
}

.ri-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
  margin-left: 16rpx;
  gap: 10rpx;
}

.status-badge {
  display: inline-block;
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  font-size: 22rpx;
  font-weight: 600;
}

.badge-visited {
  background: #e8f9ef;
  color: #07C160;
}

.badge-pending {
  background: #f5f5f5;
  color: #999;
}

.ri-reward {
  display: block;
  font-size: 24rpx;
}

.reward-done {
  color: #07C160;
}

.reward-pending {
  color: #F5A623;
}

.reward-wait {
  color: #999;
}
</style>
