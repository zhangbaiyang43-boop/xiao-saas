<template>
  <view class="page">
    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载优惠券</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <button class="primary-btn" @click="goBack">返回列表</button>
    </view>

    <view v-else-if="coupon" class="content">
      <view class="coupon-card">
        <text class="amount">¥{{ couponAmount(coupon) }}</text>
        <text class="condition">{{ couponCondition(coupon) }}</text>
        <text class="name">{{ coupon.name || '优惠券' }}</text>
        <text class="date">{{ formatDate(coupon.expire_time || coupon.valid_end_time) }} 前使用</text>
      </view>

      <view class="use-card">
        <text class="use-title">到店这样用</text>
        <text class="use-step">1. 点下面"出示核销码"</text>
        <text class="use-step">2. 给店员扫码或输入短券码</text>
        <text class="use-step">3. 核销成功后享受优惠</text>
      </view>

      <view class="info-card">
        <view class="row">
          <text class="label">短券码</text>
          <view class="value-wrap">
            <text v-if="vcLoading" class="value hint-text">正在生成券码...</text>
            <text v-else class="value short-code-val">{{ coupon.verify_code || '-' }}</text>
          </view>
        </view>
        <view class="row">
          <text class="label">状态</text>
          <text class="value">{{ couponStatusText(coupon.status) }}</text>
        </view>
        <view class="row">
          <text class="label">领取时间</text>
          <text class="value">{{ formatDateTime(coupon.created_at) }}</text>
        </view>
      </view>

      <view class="bottom-bar">
        <button v-if="coupon.status === 'UNUSED'" class="primary-btn" @click="goVerify">出示核销码</button>
        <button v-else class="disabled-btn">{{ couponStatusText(coupon.status) }}</button>
      </view>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getCouponDetail } from '@/api/coupon'
import { getCouponVerifyCode } from '@/api/verify'
import { couponStatusText, formatDate, formatDateTime, formatMoney } from '@/utils'

export default {
  setup() {
    const loading = ref(true)
    const coupon = ref(null)
    const error = ref('')
    const vcLoading = ref(false)

    const couponAmount = (item) => formatMoney(item.value ?? item.amount ?? item.discount_amount ?? 0)
    const couponCondition = (item) => {
      const min = Number(item.min_amount ?? item.threshold_amount ?? 0)
      return min > 0 ? `满 ${formatMoney(min)} 可用` : '无门槛'
    }

    const loadVerifyCode = async (id) => {
      vcLoading.value = true
      try {
        const res = await getCouponVerifyCode(id)
        if (res.code === 200 && res.data?.verify_code) {
          coupon.value = { ...coupon.value, verify_code: res.data.verify_code }
        }
      } catch (e) {
        // 静默失败，用户可去核销页查看
      } finally {
        vcLoading.value = false
      }
    }

    const loadCoupon = async (id) => {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/index/index' })
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getCouponDetail(id)
        if (res.code === 200) {
          coupon.value = res.data
          if (!coupon.value.verify_code && coupon.value.status === 'UNUSED') {
            loadVerifyCode(id)
          }
        } else {
          error.value = res.msg || '优惠券加载失败'
        }
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const goVerify = () => uni.navigateTo({ url: `/subpkg-common/pages/verify-qr?coupon_id=${coupon.value.id}` })
    const goBack = () => uni.navigateBack()

    return {
      loading,
      coupon,
      error,
      vcLoading,
      loadCoupon,
      goVerify,
      goBack,
      couponAmount,
      couponCondition,
      couponStatusText,
      formatDate,
      formatDateTime
    }
  },
  onLoad(options) {
    if (options?.id) this.loadCoupon(options.id)
    else {
      this.error = '没有找到优惠券'
      this.loading = false
    }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 28rpx;
  padding-bottom: 150rpx;
  background: #f5f7fb;
}

.state-card,
.coupon-card,
.use-card,
.info-card {
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
  border: 6rpx solid #dbeafe;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.state-title {
  display: block;
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.coupon-card {
  color: #fff;
  background: #2563eb;
  text-align: center;
}

.amount,
.condition,
.name,
.date,
.use-title,
.use-step {
  display: block;
}

.amount {
  font-size: 72rpx;
  font-weight: 900;
}

.condition {
  margin-top: 8rpx;
  font-size: 28rpx;
}

.name {
  margin-top: 26rpx;
  font-size: 34rpx;
  font-weight: 800;
}

.date {
  margin-top: 10rpx;
  color: #dbeafe;
  font-size: 24rpx;
}

.use-card,
.info-card {
  margin-top: 22rpx;
}

.use-title {
  color: #111827;
  font-size: 32rpx;
  font-weight: 800;
}

.use-step {
  margin-top: 18rpx;
  color: #334155;
  font-size: 28rpx;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 78rpx;
  border-bottom: 1rpx solid #edf2f7;
}

.row:last-child {
  border-bottom: 0;
}

.label {
  color: #64748b;
  font-size: 28rpx;
  flex-shrink: 0;
}

.value-wrap {
  flex: 1;
  text-align: right;
}

.value {
  color: #111827;
  text-align: right;
  word-break: break-all;
  font-size: 28rpx;
}

.short-code-val {
  color: #2563eb;
  font-weight: 900;
  font-size: 40rpx;
  letter-spacing: 6rpx;
  word-break: normal;
}

.hint-text {
  color: #94a3b8;
  font-size: 26rpx;
}

.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 22rpx 32rpx;
  padding-bottom: calc(22rpx + env(safe-area-inset-bottom));
  background: #fff;
  box-shadow: 0 -6rpx 20rpx rgba(15, 23, 42, 0.06);
}

.primary-btn,
.disabled-btn {
  width: 100%;
  height: 94rpx;
  border-radius: 14rpx;
  font-size: 32rpx;
  font-weight: 800;
}

.primary-btn {
  background: #2563eb;
  color: #fff;
}

.disabled-btn {
  background: #e5e7eb;
  color: #64748b;
}
</style>
