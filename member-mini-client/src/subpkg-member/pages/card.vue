<template>
  <view class="page">
    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载会员卡</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <button class="primary-btn" @click="loadProfile">刷新重试</button>
    </view>

    <view v-else>
      <view class="member-card">
        <text class="label">本店会员卡</text>
        <text class="name">{{ customer.name || '会员' }}</text>
        <text class="phone">{{ formatPhone(customer.phone) }}</text>
        <text class="id">会员编号：{{ customer.id || '-' }}</text>
      </view>

      <view class="tip-card">
        <text class="tip-title">到店这样用</text>
        <text class="tip-text">付款前告诉店员手机号，或出示优惠券二维码，就能识别会员身份并享受优惠。</text>
      </view>

      <view class="menu-card">
        <view class="menu-row" @click="go('/subpkg-coupon/pages/list')">
          <text>查看我的优惠券</text>
          <text class="arrow">></text>
        </view>
        <view class="menu-row" @click="go('/subpkg-common/pages/verify-qr')">
          <text>出示给店员</text>
          <text class="arrow">></text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getMemberProfile } from '@/api/auth'
import { formatPhone } from '@/utils'

export default {
  setup() {
    const loading = ref(false)
    const error = ref('')
    const customer = ref({})

    const loadProfile = async () => {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/mine/mine' })
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getMemberProfile()
        if (res.code === 200) customer.value = res.data || {}
        else error.value = res.msg || '会员卡加载失败'
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const go = (url) => uni.navigateTo({ url })

    return { loading, error, customer, loadProfile, go, formatPhone }
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
.member-card,
.tip-card,
.menu-card {
  padding: 34rpx;
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
  border: 6rpx solid #d1fae5;
  border-top-color: #07C160;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.state-title,
.label,
.name,
.phone,
.id,
.tip-title,
.tip-text {
  display: block;
}

.state-title {
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.member-card {
  color: #fff;
  background: #07C160;
  box-shadow: 0 10rpx 28rpx rgba(7, 193, 96, 0.24);
}

.label {
  color: #cbd5e1;
  font-size: 26rpx;
}

.name {
  margin-top: 34rpx;
  font-size: 48rpx;
  font-weight: 900;
}

.phone {
  margin-top: 12rpx;
  color: #e2e8f0;
  font-size: 30rpx;
}

.id {
  margin-top: 48rpx;
  color: #cbd5e1;
  font-size: 24rpx;
  word-break: break-all;
}

.tip-card,
.menu-card {
  margin-top: 22rpx;
}

.tip-title {
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.tip-text {
  margin-top: 14rpx;
  color: #64748b;
  font-size: 28rpx;
  line-height: 1.6;
}

.menu-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 86rpx;
  border-bottom: 1rpx solid #edf2f7;
  color: #111827;
  font-size: 30rpx;
  font-weight: 700;
}

.menu-row:last-child {
  border-bottom: 0;
}

.arrow {
  color: #94a3b8;
}

.primary-btn {
  width: 100%;
  height: 92rpx;
  margin-top: 28rpx;
  border-radius: 24rpx;
  background: #07C160;
  color: #fff;
  font-size: 30rpx;
  font-weight: 800;
}
</style>

