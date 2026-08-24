<template>
  <view class="page">
    <view class="header">
      <state-hero-stat
        :loading="loading"
        :error="!!error"
        :value="balance"
        label="我的积分"
        loading-label="正在加载积分…"
        error-label="加载失败，点击重试"
        @retry="load"
      />
    </view>

    <!-- 积分规则 -->
    <view class="rules-card">
      <text class="rules-title">积分规则</text>
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
        <text class="rule-icon">🎫</text>
        <view class="rule-text">
          <text class="rule-main">攒够自动兑券</text>
          <text class="rule-desc">积分每攒够 1000 分，自动为你兑换一张优惠券，无需手动兑换，去"我的优惠券"查看</text>
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
      <state-loading text="加载中" />
    </view>

    <view v-else-if="error" class="state-wrap">
      <state-error :title="error" retry-text="刷新重试" @retry="load" />
    </view>

    <view v-else-if="!records.length" class="state-wrap">
      <state-empty title="暂无积分记录" desc="消费后自动获得积分，1元 = 1积分" />
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
import StateHeroStat from '@/components/state-hero-stat/state-hero-stat.vue'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'
import StateEmpty from '@/components/state-empty/state-empty.vue'

export default {
  components: { StateHeroStat, StateLoading, StateError, StateEmpty },
  setup() {
    const balance = ref(0)
    const records = ref([])
    const loading = ref(false)
    const error = ref('')

    const load = async () => {
      loading.value = true
      error.value = ''
      try {
        const res = await getPointsHistory(0, 50)
        if (res.code === 200) {
          balance.value = res.data.balance ?? 0
          records.value = res.data.records || []
        } else {
          error.value = res.msg || '加载失败'
        }
      } catch (e) {
        error.value = '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const formatDate = (s) => {
      if (!s) return ''
      return s.slice(0, 10)
    }

    return { balance, records, loading, error, load, formatDate }
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
  background: var(--brand);
  padding: 60rpx 40rpx 48rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
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

  &.plus { color: var(--brand); }
  &.minus { color: #6b7280; }
}
</style>
