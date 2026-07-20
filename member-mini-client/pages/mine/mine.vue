<template>
  <view class="page">
    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <text class="state-desc">请刷新或重新扫码进入。</text>
      <button class="primary-btn" @click="loadProfile">重新加载</button>
    </view>

    <view v-else>
      <view class="profile-card">
        <text class="name">{{ customer.name || '会员' }}</text>
        <text class="phone">{{ formatPhone(customer.phone) }}</text>
        <text class="desc">这里可以查看会员资料、优惠券、消费记录和邀请奖励。</text>
      </view>

      <view class="info-card">
        <view class="row">
          <text class="label">会员编号</text>
          <text class="value">{{ customer.customer_id || customer.id || '-' }}</text>
        </view>
        <view class="row">
          <text class="label">加入门店</text>
          <text class="value">{{ customer.tenant_name || tenantName || '-' }}</text>
        </view>
        <view class="row">
          <text class="label">最近消费</text>
          <text class="value">{{ formatDateTime(customer.last_consume_time) }}</text>
        </view>
      </view>

      <view class="menu-card">
        <view class="menu-row" @click="go('/subpkg-coupon/pages/list')">
          <text>我的优惠券</text>
          <text class="arrow">></text>
        </view>
        <view class="menu-row" @click="go('/subpkg-member/pages/invite')">
          <text>我的邀请</text>
          <text class="arrow">></text>
        </view>
        <view class="menu-row" @click="go('/subpkg-member/pages/consumptions')">
          <text>消费记录</text>
          <text class="arrow">></text>
        </view>
      </view>

      <button class="logout" @click="logout">退出当前会员</button>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getMemberProfile } from '@/api/auth'
import { clearCustomerSession } from '@/utils/auth'
import { formatDateTime, formatPhone } from '@/utils'

export default {
  setup() {
    const customer = ref({})
    const loading = ref(false)
    const error = ref('')
    const tenantName = ref(uni.getStorageSync('tenant_name') || '')

    const loadProfile = async () => {
      if (!uni.getStorageSync('customer_token')) {
        error.value = '还没有登录会员'
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getMemberProfile()
        if (res.code === 200) customer.value = res.data || {}
        else error.value = res.msg || '资料加载失败'
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const go = (url) => uni.navigateTo({ url })

    const logout = () => {
      clearCustomerSession()
      uni.showToast({ title: '已退出', icon: 'success' })
      setTimeout(() => {
        uni.reLaunch({ url: '/pages/index/index' })
      }, 600)
    }

    return { customer, loading, error, tenantName, loadProfile, go, logout, formatDateTime, formatPhone }
  },
  onShow() {
    this.loadProfile()
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 28rpx;
  background: #f5f7fb;
}

.state-card,
.profile-card,
.info-card,
.menu-card {
  padding: 30rpx;
  background: #fff;
  border-radius: 20rpx;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.05);
}

.state-card {
  margin-top: 120rpx;
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

.state-title,
.state-desc,
.name,
.phone,
.desc {
  display: block;
}

.state-title {
  color: #111827;
  font-size: 32rpx;
  font-weight: 700;
}

.state-desc {
  margin-top: 10rpx;
  color: #64748b;
  font-size: 26rpx;
}

.profile-card {
  color: #fff;
  background: #1f2937;
}

.name {
  font-size: 42rpx;
  font-weight: 800;
}

.phone {
  margin-top: 10rpx;
  color: #cbd5e1;
  font-size: 28rpx;
}

.desc {
  margin-top: 28rpx;
  color: #e2e8f0;
  font-size: 26rpx;
}

.info-card,
.menu-card {
  margin-top: 22rpx;
}

.row,
.menu-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 80rpx;
  border-bottom: 1rpx solid #edf2f7;
  font-size: 28rpx;
}

.row:last-child,
.menu-row:last-child {
  border-bottom: 0;
}

.label {
  color: #64748b;
}

.value {
  max-width: 420rpx;
  color: #111827;
  text-align: right;
  word-break: break-all;
}

.arrow {
  color: #94a3b8;
}

.primary-btn,
.logout {
  width: 100%;
  height: 94rpx;
  border-radius: 14rpx;
  font-size: 30rpx;
  font-weight: 700;
}

.primary-btn {
  margin-top: 28rpx;
  background: #2563eb;
  color: #fff;
}

.logout {
  margin-top: 28rpx;
  background: #ef4444;
  color: #fff;
}
</style>
