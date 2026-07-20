<template>
  <view class="page">

    <!-- ① Skeleton — renders instantly, eliminates white screen -->
    <view v-if="loading && !verify.code" class="card skeleton-card">
      <view class="sk sk-title"></view>
      <view class="sk sk-desc"></view>
      <view class="sk sk-qr"></view>
      <view class="sk-code-area">
        <view class="sk sk-label"></view>
        <view class="sk sk-code"></view>
      </view>
    </view>

    <!-- ② Success — vibration + amount + member tail triggered by markVerified() -->
    <view v-else-if="verified" class="card state-card success-card">
      <view class="success-ring">
        <text class="success-check">✓</text>
      </view>
      <text class="state-title">核销成功</text>
      <text v-if="verifyAmount" class="success-amount">已优惠 ¥{{ verifyAmount }}</text>
      <text v-if="memberTail" class="success-member">尾号{{ memberTail }}会员</text>
      <text class="state-desc">优惠已确认，感谢光临。</text>
      <button class="primary-btn" @click="goCoupons">查看我的优惠券</button>
      <button class="plain-btn" @click="goHome">返回会员中心</button>
    </view>

    <!-- ③ Error — always show short code as manual fallback -->
    <view v-else-if="error" class="card state-card">
      <text class="state-title">{{ error }}</text>
      <text class="state-desc">让店员输入下面的短券码，也可以完成核销。</text>
      <text v-if="shortCode" class="fallback-code">{{ shortCode }}</text>
      <button class="primary-btn" @click="loadCode">重新生成二维码</button>
    </view>

    <!-- ④ Normal — QR显示（后台刷新时叠加 spinner，不打断显示） -->
    <view v-else class="card">
      <text class="title">到店出示这个二维码</text>
      <text class="desc">店员扫码后，本页会自动提示核销结果。</text>

      <view class="qr-box">
        <canvas canvas-id="couponQrCanvas" id="couponQrCanvas" class="qr-canvas"></canvas>
        <!-- refresh overlay: only shows when loading AND we already have a cached QR -->
        <view v-if="loading" class="qr-refresh-mask">
          <view class="spinner"></view>
        </view>
      </view>

      <view class="coupon-info">
        <text class="coupon-name">{{ verify.name || '优惠券' }}</text>
        <text class="coupon-value">{{ couponText }}</text>
      </view>

      <!-- Short code — large, prominent, 0 learning cost -->
      <view class="code-box">
        <text class="code-label">扫码失败时，请让店员输入短券码</text>
        <text class="code-text short-code">{{ shortCode }}</text>
      </view>

      <view class="info">
        <text>会员：{{ memberDisplay }}</text>
        <text>门店：{{ verify.tenant_id || tenantId || '-' }}</text>
      </view>
    </view>

  </view>
</template>

<script>
import { getCouponDetail } from '@/api/coupon'
import { getCouponVerifyCode, getMemberVerifyCode } from '@/api/verify'
import { drawQrCode } from '@/utils/qrcode-canvas'

const CACHE_PREFIX = 'vqr_'
const POLL_INTERVAL = 8000    // 8s — was 3s (too aggressive)
const MAX_POLLS     = 15      // stop after ~2 min, avoid zombie requests
const REFRESH_MIN   = 30      // seconds

export default {
  data() {
    return {
      loading:    false,
      error:      '',
      verified:   false,
      verify:     {},
      couponId:   '',
      pollTimer:  null,
      pollCount:  0,
      refreshTimer: null,
      customerId: uni.getStorageSync('customer_id') || '',
      tenantId:   uni.getStorageSync('tenant_id')   || ''
    }
  },
  computed: {
    displayCode() {
      return this.verify.code || this.verify.qr_code || ''
    },
    shortCode() {
      return this.verify.verify_code || ''
    },
    couponText() {
      const value = Number(this.verify.value || 0)
      const min   = Number(this.verify.min_amount || 0)
      if (!value) return '请向店员出示'
      return min > 0 ? `满${min}减${value}` : `立减${value}`
    },
    verifyAmount() {
      const v = Number(this.verify.value || 0)
      return v > 0 ? v : ''
    },
    memberTail() {
      const id = String(this.verify.customer_id || this.customerId || '')
      return id.length >= 4 ? id.slice(-4) : id
    },
    memberDisplay() {
      return this.memberTail
        ? `尾号${this.memberTail}会员`
        : (this.verify.customer_id || this.customerId || '-')
    }
  },

  onLoad(options) {
    this.couponId = options?.coupon_id || ''
    this._loadCache()   // show cached QR immediately — no white screen
  },
  onShow()   { this.loadCode() },
  onHide()   { this.stopPolling(); this.stopRefresh() },
  onUnload() { this.stopPolling(); this.stopRefresh() },

  methods: {
    // ── Cache ────────────────────────────────────────────────────────
    _cacheKey() { return CACHE_PREFIX + (this.couponId || 'member') },

    _loadCache() {
      try {
        const raw = uni.getStorageSync(this._cacheKey())
        if (!raw) return
        const data = JSON.parse(raw)
        // Use cache only if fresh (≤ 55 s — matches refresh_after default)
        if (data && Date.now() - (data._ts || 0) <= 55000) {
          this.verify = data
          this.$nextTick(() => this.drawQr())
        }
      } catch (_) {}
    },

    _saveCache(data) {
      try {
        uni.setStorageSync(this._cacheKey(), JSON.stringify({ ...data, _ts: Date.now() }))
      } catch (_) {}
    },

    // ── Network guard ────────────────────────────────────────────────
    _isOnline() {
      return new Promise((resolve) => {
        uni.getNetworkType({
          success: ({ networkType }) => resolve(networkType !== 'none'),
          fail: () => resolve(true)
        })
      })
    },

    // ── Load ─────────────────────────────────────────────────────────
    async loadCode() {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/index/index' })
        return
      }

      const online = await this._isOnline()
      if (!online) {
        if (!this.verify.code) this.error = '当前网络不可用，请检查网络后重试'
        return
      }

      this.loading  = true
      this.error    = ''
      this.verified = false
      this.pollCount = 0
      this.stopPolling()
      this.stopRefresh()

      try {
        const res = this.couponId
          ? await getCouponVerifyCode(this.couponId)
          : await getMemberVerifyCode()

        if (res.code !== 200 || !res.data?.code) {
          const used = await this.checkCouponStatus(true)
          if (!used) this.error = res.msg || '核销码生成失败'
          return
        }

        this.verify = {
          ...res.data,
          customer_id: res.data.customer_id || this.customerId,
          tenant_id:   res.data.tenant_id   || this.tenantId
        }
        this._saveCache(this.verify)
        this.$nextTick(() => this.drawQr())
        this.startPolling()
        this.startRefresh()
      } catch (err) {
        const used = await this.checkCouponStatus(true)
        if (!used) this.error = err.message || '核销码生成失败'
      } finally {
        this.loading = false
      }
    },

    drawQr() {
      if (!this.displayCode) return
      drawQrCode({ canvasId: 'couponQrCanvas', text: this.displayCode, size: 220, context: this })
    },

    // ── Polling — 8s, capped at MAX_POLLS ────────────────────────────
    startPolling() {
      if (!this.couponId || this.verified) return
      this.stopPolling()
      this.pollTimer = setInterval(() => {
        if (this.pollCount >= MAX_POLLS) { this.stopPolling(); return }
        this.pollCount++
        this.checkCouponStatus(false)
      }, POLL_INTERVAL)
    },

    startRefresh() {
      const after = Math.max(Number(this.verify.refresh_after || 55), REFRESH_MIN)
      this.stopRefresh()
      this.refreshTimer = setInterval(() => {
        if (!this.verified && !this.loading) this.loadCode()
      }, after * 1000)
    },

    stopRefresh() { clearInterval(this.refreshTimer); this.refreshTimer = null },
    stopPolling()  { clearInterval(this.pollTimer);   this.pollTimer   = null },

    async checkCouponStatus(doToast = false) {
      if (!this.couponId) return false
      try {
        const res = await getCouponDetail(this.couponId)
        if (String(res?.data?.status || '').toUpperCase() === 'USED') {
          this.markVerified(doToast)
          return true
        }
      } catch (_) {}
      return false
    },

    markVerified(doToast = false) {
      this.verified = true
      this.error    = ''
      this.stopPolling()
      this.stopRefresh()
      try { uni.vibrateLong() } catch (_) {}           // haptic feedback
      if (doToast) uni.showToast({ title: '核销成功', icon: 'success' })
    },

    goCoupons() { uni.redirectTo({ url: '/subpkg-coupon/pages/list' }) },
    goHome()    { uni.reLaunch({ url: '/pages/index/index' }) }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 28rpx;
  background: #f5f7fb;
}

/* ── Skeleton ─────────────────────────────────────────────────── */
.skeleton-card { margin-top: 24rpx; }
.sk {
  background: #e2e8f0;
  border-radius: 12rpx;
  animation: shimmer 1.4s ease-in-out infinite;
}
@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50%       { opacity: .4; }
}
.sk-title { height: 44rpx; width: 60%; margin: 0 auto 16rpx; }
.sk-desc  { height: 30rpx; width: 80%; margin: 0 auto 36rpx; }
.sk-qr    { width: 500rpx; height: 500rpx; border-radius: 24rpx; margin: 0 auto 32rpx; }
.sk-code-area {
  padding: 24rpx;
  border-radius: 20rpx;
  background: #f8fafc;
}
.sk-label { height: 24rpx; width: 70%; margin-bottom: 18rpx; }
.sk-code  { height: 72rpx; width: 55%; margin: 0 auto; }

/* ── Card ─────────────────────────────────────────────────────── */
.card {
  padding: 40rpx 32rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.05);
  text-align: center;
}
.state-card { margin-top: 120rpx; }

/* ── Success ──────────────────────────────────────────────────── */
.success-card { border: 2rpx solid #bbf7d0; }

.success-ring {
  width: 120rpx;
  height: 120rpx;
  margin: 0 auto 28rpx;
  border-radius: 50%;
  background: #16a34a;
  display: flex;
  align-items: center;
  justify-content: center;
}
.success-check {
  display: block;
  color: #fff;
  font-size: 72rpx;
  font-weight: 900;
  line-height: 1;
}
.success-amount {
  display: block;
  margin-top: 16rpx;
  color: #16a34a;
  font-size: 60rpx;
  font-weight: 900;
}
.success-member {
  display: block;
  margin-top: 8rpx;
  color: #64748b;
  font-size: 28rpx;
}

/* ── Spinner / states ─────────────────────────────────────────── */
.spinner {
  width: 56rpx;
  height: 56rpx;
  margin: 0 auto;
  border: 6rpx solid #dbeafe;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin .9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.title, .desc, .state-title, .state-desc,
.info text, .coupon-name, .coupon-value,
.code-label, .code-text, .fallback-code { display: block; }

.title    { color: #111827; font-size: 42rpx; font-weight: 900; }
.desc     { margin-top: 14rpx; color: #64748b; font-size: 28rpx; line-height: 1.6; }
.state-title { color: #111827; font-size: 36rpx; font-weight: 900; }
.state-desc  { margin-top: 14rpx; color: #64748b; font-size: 28rpx; line-height: 1.6; }

/* ── QR ───────────────────────────────────────────────────────── */
.qr-box {
  position: relative;
  width: 500rpx;
  height: 500rpx;
  margin: 42rpx auto 24rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 16rpx solid #111827;
  border-radius: 28rpx;
  background: #fff;
}
.qr-canvas { width: 220px; height: 220px; }
.qr-refresh-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,.72);
  border-radius: 20rpx;
}

/* ── Coupon info ──────────────────────────────────────────────── */
.coupon-info  { margin-bottom: 26rpx; }
.coupon-name  { color: #111827; font-size: 32rpx; font-weight: 900; }
.coupon-value { margin-top: 8rpx; color: #2563eb; font-size: 28rpx; font-weight: 800; }

/* ── Short code ───────────────────────────────────────────────── */
.code-box   { padding: 24rpx; border-radius: 20rpx; background: #f8fafc; }
.code-label { color: #64748b; font-size: 24rpx; }
.code-text  { margin-top: 10rpx; color: #111827; font-size: 34rpx; font-weight: 900; word-break: break-all; }
.short-code { font-size: 72rpx; font-weight: 900; letter-spacing: 10rpx; color: #111827; word-break: normal; }

/* Fallback short code in error state — blue + large */
.fallback-code {
  margin: 24rpx auto 16rpx;
  font-size: 72rpx;
  font-weight: 900;
  letter-spacing: 10rpx;
  color: #2563eb;
  word-break: normal;
}

/* ── Info ─────────────────────────────────────────────────────── */
.info { margin-top: 24rpx; color: #64748b; font-size: 24rpx; line-height: 1.7; }

/* ── Buttons ──────────────────────────────────────────────────── */
.primary-btn, .plain-btn {
  width: 100%;
  height: 94rpx;
  margin-top: 28rpx;
  border-radius: 14rpx;
  font-size: 32rpx;
  font-weight: 800;
}
.primary-btn { background: #2563eb; color: #fff; }
.plain-btn   { background: #f8fafc; color: #111827; border: 2rpx solid #e2e8f0; }
</style>
