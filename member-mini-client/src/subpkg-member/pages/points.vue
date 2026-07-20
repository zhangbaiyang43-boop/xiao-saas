<template>
  <view class="page">
    <view class="header">
      <text class="balance">{{ balance }}</text>
      <text class="balance-label">我的积分</text>
    </view>

    <!-- 获取规则 -->
    <view class="rules-card">
      <text class="rules-title">积分获取规则</text>
      <view class="rule-row">
        <text class="rule-icon">🛒</text>
        <view class="rule-text">
          <text class="rule-main">消费获积分</text>
          <text class="rule-desc">每消费 1 元获得 1 积分，支付成功后自动到账</text>
        </view>
      </view>
      <view class="rule-row">
        <text class="rule-icon">🎁</text>
        <view class="rule-text">
          <text class="rule-main">注册奖励</text>
          <text class="rule-desc">首次加入会员赠送积分，查看记录确认到账</text>
        </view>
      </view>
      <view class="rule-row">
        <text class="rule-icon">📅</text>
        <view class="rule-text">
          <text class="rule-main">积分有效期</text>
          <text class="rule-desc">积分自获得之日起 365 天内有效，到期自动清零</text>
        </view>
      </view>
    </view>

    <view v-if="loading" class="state-wrap">
      <view class="loading-ring"></view>
      <text class="state-text">加载中</text>
    </view>

    <view v-else-if="!records.length" class="state-wrap">
      <text class="state-text">暂无积分记录</text>
      <text class="state-sub">消费后自动获得积分，1元 = 1积分</text>
    </view>

    <view v-else class="record-list">
      <view v-for="r in records" :key="r.id" class="record-item">
        <view class="ri-left">
          <text class="ri-label">{{ r.label }}</text>
          <text class="ri-remark">{{ r.remark || '' }}</text>
          <text class="ri-date">{{ formatDate(r.created_at) }}</text>
        </view>
        <text :class="['ri-points', r.points >= 0 ? 'plus' : 'minus']">
          {{ r.points >= 0 ? '+' : '' }}{{ r.points }}
        </text>
      </view>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getPointsHistory } from '@/api/auth'

export default {
  setup() {
    const balance = ref(0)
    const records = ref([])
    const loading = ref(false)

    const load = async () => {
      loading.value = true
      try {
        const res = await getPointsHistory(0, 50)
        if (res.code === 200) {
          balance.value = res.data.balance ?? 0
          records.value = res.data.records || []
        }
      } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
      } finally {
        loading.value = false
      }
    }

    const formatDate = (s) => {
      if (!s) return ''
      return s.slice(0, 10)
    }

    return { balance, records, loading, load, formatDate }
  },
  onShow() { this.load() }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #f5f7fb;
}

.header {
  background: #ea580c;
  padding: 60rpx 40rpx 48rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.balance {
  font-size: 80rpx;
  font-weight: 900;
  color: #fff;
  line-height: 1;
}

.balance-label {
  margin-top: 12rpx;
  font-size: 26rpx;
  color: rgba(255,255,255,0.8);
}

.rules-card {
  margin: 22rpx 28rpx 0;
  background: #fff;
  border-radius: 20rpx;
  padding: 28rpx 30rpx;
}

.rules-title {
  display: block;
  font-size: 26rpx;
  font-weight: 700;
  color: #374151;
  margin-bottom: 20rpx;
}

.rule-row {
  display: flex;
  align-items: flex-start;
  gap: 18rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f3f4f6;

  &:last-child { border-bottom: 0; }
}

.rule-icon { font-size: 34rpx; line-height: 1.4; }

.rule-text { flex: 1; }

.rule-main {
  display: block;
  font-size: 28rpx;
  color: #111827;
  font-weight: 600;
}

.rule-desc {
  display: block;
  margin-top: 4rpx;
  font-size: 24rpx;
  color: #9ca3af;
  line-height: 1.5;
}

.state-wrap {
  padding: 80rpx 40rpx;
  text-align: center;
}

.loading-ring {
  width: 56rpx;
  height: 56rpx;
  margin: 0 auto 22rpx;
  border: 6rpx solid #fed7aa;
  border-top-color: #ea580c;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.state-text { display: block; font-size: 28rpx; color: #6b7280; }
.state-sub { display: block; margin-top: 10rpx; font-size: 24rpx; color: #9ca3af; }

.record-list {
  margin: 22rpx 28rpx;
  background: #fff;
  border-radius: 20rpx;
  overflow: hidden;
}

.record-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 32rpx;
  border-bottom: 1rpx solid #f3f4f6;

  &:last-child { border-bottom: 0; }
}

.ri-left { flex: 1; }
.ri-label { display: block; font-size: 28rpx; color: #111827; font-weight: 600; }
.ri-remark { display: block; margin-top: 4rpx; font-size: 24rpx; color: #9ca3af; }
.ri-date { display: block; margin-top: 4rpx; font-size: 22rpx; color: #c8c9cc; }

.ri-points {
  font-size: 36rpx;
  font-weight: 800;

  &.plus { color: #ea580c; }
  &.minus { color: #6b7280; }
}
</style>
