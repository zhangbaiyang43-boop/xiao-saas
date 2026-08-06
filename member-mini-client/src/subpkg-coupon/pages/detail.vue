<template>
  <view class="page">

    <!-- 加载态 -->
    <view v-if="loading" class="state-wrap">
      <state-loading text="正在加载优惠券" />
    </view>

    <!-- 错误态 -->
    <view v-else-if="error" class="state-wrap">
      <state-error :title="error" retry-text="返回列表" @retry="goBack" />
    </view>

    <!-- 详情 -->
    <view v-else-if="coupon" class="content">

      <!-- 顶部金额卡 -->
      <view class="amount-card">
        <view class="ac-left">
          <text class="ac-amount">¥{{ couponAmount(coupon) }}</text>
          <text class="ac-cond">{{ couponCondition(coupon) }}</text>
        </view>
        <view class="ac-right">
          <text class="ac-name">{{ coupon.name || '优惠券' }}</text>
          <text class="ac-date">{{ formatDate(coupon.expire_time || coupon.valid_end_time) }} 前使用</text>
          <view :class="['ac-badge', coupon.status === 'UNUSED' ? 'badge-active' : 'badge-inactive']">
            {{ couponStatusText(coupon.status) }}
          </view>
        </view>
      </view>

      <!-- 使用方法 -->
      <view class="card">
          <text class="card-title">到店这样用</text>
        <view class="steps">
          <view class="step-item">
            <view class="step-num">1</view>
            <text class="step-text">在小程序里选好菜</text>
          </view>
          <view class="step-item">
            <view class="step-num">2</view>
            <text class="step-text">结算时自动为您选中这张券</text>
          </view>
          <view class="step-item">
            <view class="step-num">3</view>
            <text class="step-text">支付成功即自动核销，享受优惠</text>
          </view>
        </view>
      </view>

      <!-- 详细信息 -->
      <view class="card info-card">
        <view class="info-row">
          <text class="info-label">状态</text>
          <text class="info-value">{{ couponStatusText(coupon.status) }}</text>
        </view>
        <view class="info-divider"></view>
        <view class="info-row">
          <text class="info-label">领取时间</text>
          <text class="info-value">{{ formatDateTime(coupon.created_at) }}</text>
        </view>
      </view>

      <!-- 底部操作栏 -->
      <view class="bottom-bar">
        <button
          v-if="coupon.status === 'UNUSED'"
          class="btn-primary"
          @click="goOrder"
        >去点餐</button>
        <button v-else class="btn-disabled">{{ couponStatusText(coupon.status) }}</button>
      </view>

    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getCouponDetail } from '@/api/coupon'
import { couponStatusText, formatDate, formatDateTime, formatMoney } from '@/utils'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'

export default {
  components: { StateLoading, StateError },
  setup() {
    const loading = ref(true)
    const coupon = ref(null)
    const error = ref('')

    const couponAmount = (item) => formatMoney(item.value ?? item.amount ?? item.discount_amount ?? 0)
    const couponCondition = (item) => {
      const min = Number(item.min_amount ?? item.threshold_amount ?? 0)
      return min > 0 ? `满 ${formatMoney(min)} 可用` : '无门槛'
    }

    const loadCoupon = async (id) => {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/mine/mine' })
        return
      }

      loading.value = true
      error.value = ''
      try {
        const res = await getCouponDetail(id)
        if (res.code === 200) {
          coupon.value = res.data
        } else {
          error.value = res.msg || '优惠券加载失败'
        }
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    // 去点餐：优惠券在结算时自动核销，不再需要店员扫码——回到点餐页并定位到"点餐"标签
    const goOrder = () => {
      // 写不进这个本地标记最多回到点餐页时没有自动定位到"点餐"标签，不影响能不能点餐。
      // eslint-disable-next-line no-empty
      try { uni.setStorageSync('menu_focus_tab', 'order') } catch (_) {}
      const pages = getCurrentPages()
      const idx = pages.findIndex(p => (p.route || '').indexOf('subpkg-order/pages/menu') !== -1)
      if (idx >= 0) {
        uni.navigateBack({ delta: pages.length - 1 - idx })
      } else {
        uni.showToast({ title: '请先扫桌台二维码点餐', icon: 'none' })
      }
    }
    const goBack = () => uni.navigateBack()

    return {
      loading,
      coupon,
      error,
      loadCoupon,
      goOrder,
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
  background: #F7F8FA;
  padding-bottom: calc(160rpx + env(safe-area-inset-bottom));
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
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

/* ── 内容区 ──────────────────────────────── */
.content {
  padding-bottom: 32rpx;
}

/* ── 顶部金额卡 ───────────────────────────── */
.amount-card {
  display: flex;
  align-items: stretch;
  overflow: hidden;
}

/* 红金票券配色，右边缘打一个圆孔，呼应"撕票根"的实体票券质感，和列表页/领券卡片统一 */
.ac-left {
  flex-shrink: 0;
  width: 220rpx;
  background: linear-gradient(160deg, #ff5a3c, #ff2f1f 55%, #d81717);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48rpx 16rpx;
  position: relative;
}

.ac-left::after {
  content: "";
  position: absolute;
  right: -10rpx;
  top: 50%;
  transform: translateY(-50%);
  width: 20rpx;
  height: 20rpx;
  border-radius: 50%;
  background: #fff;
}

.ac-amount {
  display: block;
  color: #fff;
  font-size: 72rpx;
  font-weight: bold;
  line-height: 1;
}

.ac-cond {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.85);
  font-size: 24rpx;
  text-align: center;
}

.ac-right {
  flex: 1;
  background: #fff;
  padding: 40rpx 28rpx;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.ac-name {
  display: block;
  color: #111;
  font-size: 36rpx;
  font-weight: bold;
}

.ac-date {
  display: block;
  margin-top: 12rpx;
  color: #999;
  font-size: 26rpx;
}

.ac-badge {
  display: inline-block;
  margin-top: 16rpx;
  padding: 6rpx 20rpx;
  border-radius: 12rpx;
  font-size: 24rpx;
  font-weight: 600;
}

.badge-active {
  background: #e8f9ef;
  color: #07C160;
}

.badge-inactive {
  background: #f5f5f5;
  color: #999;
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
  margin-bottom: 24rpx;
}

/* ── 使用步骤 ─────────────────────────────── */
.steps {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.step-num {
  flex-shrink: 0;
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: #07C160;
  color: #fff;
  font-size: 26rpx;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-text {
  color: #333;
  font-size: 30rpx;
  line-height: 1.4;
}

/* ── 信息列表 ─────────────────────────────── */
.info-card {
  padding: 0 32rpx;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 88rpx;
  padding: 0;
}

.info-divider {
  height: 2rpx;
  background: #F7F8FA;
}

.info-label {
  flex-shrink: 0;
  color: #999;
  font-size: 30rpx;
}

.info-value {
  color: #111;
  font-size: 30rpx;
  text-align: right;
}


/* ── 底部操作栏 ───────────────────────────── */
.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 16rpx 32rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff;
  box-shadow: 0 -2rpx 12rpx rgba(0, 0, 0, 0.08);
  z-index: 100;
}

/* ── 通用按钮 ─────────────────────────────── */
.btn-primary {
  display: block;
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  background: #07C160;
  color: #fff;
  font-size: 36rpx;
  font-weight: 700;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}

.btn-disabled {
  display: block;
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  background: #e8e8e8;
  color: #999;
  font-size: 36rpx;
  font-weight: 600;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}
</style>

