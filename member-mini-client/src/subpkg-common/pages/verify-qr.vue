﻿﻿﻿<template>
  <view class="page">

    <!-- ① Skeleton -->
    <view v-if="loading && !verify.code" class="card skeleton-card">
      <view class="sk sk-title"></view>
      <view class="sk sk-desc"></view>
      <view class="sk sk-qr"></view>
      <view class="sk-code-area">
        <view class="sk sk-label"></view>
        <view class="sk sk-code"></view>
      </view>
    </view>

    <!-- ② 核销成功 -->
    <view v-else-if="verified" class="card state-card success-card">
      <view class="success-ring">
        <text class="success-check">✓</text>
      </view>
      <text class="state-title">核销成功</text>
      <text v-if="verifyAmount" class="success-amount">已优惠 ¥{{ verifyAmount }}</text>
      <text v-if="memberTail" class="success-member">尾号{{ memberTail }}会员</text>
      <text class="state-desc">优惠已确认，感谢光临。</text>
      <button class="btn-primary mt32" @click="goCoupons">查看我的优惠券</button>
      <button class="btn-plain mt16" @click="goHome">返回我的</button>
    </view>

    <!-- ③ 错误态 -->
    <view v-else-if="error" class="card state-card">
      <text class="state-title">{{ error }}</text>
      <text v-if="couponExpired" class="state-desc">这张优惠券已过期，无法继续使用。您可以查看其他可用优惠券。</text>
      <text v-else class="state-desc">让店员输入下面的短券码，也可以完成核销。</text>
      <view v-if="shortCode && !couponExpired" class="fallback-box">
        <text class="fallback-code">{{ shortCode }}</text>
      </view>
      <button v-if="!couponExpired" class="btn-primary mt32" @click="loadCode">重新生成二维码</button>
      <button class="btn-primary mt32" @click="goCoupons">查看我的优惠券</button>
    </view>

    <!-- ④ 正常显示二维码 -->
    <view v-else class="card">
      <text class="qr-title">请让店员扫码</text>
      <text class="qr-desc">扫码后本页会自动显示使用结果。</text>
      <view class="coupon-info-bar">
        <text class="cib-name">{{ verify.name || '优惠券' }}</text>
        <text class="cib-value">{{ couponText }}</text>
      </view>
      <view class="qr-box">
        <canvas canvas-id="couponQrCanvas" id="couponQrCanvas" class="qr-canvas"></canvas>
        <view v-if="loading" class="qr-refresh-mask">
          <view class="loading-ring-sm"></view>
        </view>
      </view>
      <view class="code-box">
        <text class="code-label">扫码失败时输入这个短券码</text>
        <text class="short-code">{{ shortCode }}</text>
      </view>
      <view class="member-info">
        <text class="mi-text">会员：{{ memberDisplay }}</text>
        <text class="mi-text">门店：{{ tenantName || '-' }}</text>
      </view>
    </view>

    <!-- ⑤ 新券到账庆祝遮罩 -->
    <view v-if="newCouponOverlay" class="nc-overlay" @click="dismissNewCoupon">

      <!-- 彩带粒子（纯 CSS 动画） -->
      <view class="confetti">
        <view v-for="i in 12" :key="i" class="confetti-item" :class="`ci-${i}`"></view>
      </view>

      <!-- 主卡片 -->
      <view class="nc-card" @click.stop>

        <!-- 顶部光晕 -->
        <view class="nc-glow"></view>

        <!-- 标题区 -->
        <view class="nc-header">
          <text class="nc-emoji">🎉</text>
          <text class="nc-title">新券到账</text>
          <text class="nc-subtitle">下次来还有优惠，记得用哦！</text>
        </view>

        <!-- 券体 -->
        <view class="nc-coupon-body">
          <!-- 锯齿边 -->
          <view class="nc-serration nc-serration-left"></view>
          <view class="nc-serration nc-serration-right"></view>

          <view class="nc-coupon-left">
            <text class="nc-amount">
              <text class="nc-amount-sign">¥</text>{{ newCouponOverlay.amountInt }}
              <text v-if="newCouponOverlay.amountDec" class="nc-amount-dec">.{{ newCouponOverlay.amountDec }}</text>
            </text>
            <text class="nc-min">{{ newCouponOverlay.minText }}</text>
          </view>

          <view class="nc-divider"></view>

          <view class="nc-coupon-right">
            <text class="nc-coupon-name">{{ newCouponOverlay.name }}</text>
            <text class="nc-coupon-expire">{{ newCouponOverlay.expireText }}</text>
          </view>
        </view>

        <!-- 操作按钮 -->
        <button class="nc-btn-primary" @click="goUseCoupon">立即查看优惠券</button>
        <button class="nc-btn-plain" @click="dismissNewCoupon">稍后再说</button>
      </view>
    </view>

  </view>
</template>

<script>
import { getCouponDetail, getCustomerCoupons } from '@/api/coupon'
import { getCouponVerifyCode } from '@/api/verify'
import { drawQrCode } from '@/utils/qrcode-canvas'

const CACHE_PREFIX  = 'vqr_'
const POLL_INTERVAL = 8000
const MAX_POLLS     = 15
const REFRESH_MIN   = 30
const CACHE_MAX_AGE = 250000

export default {
  data() {
    return {
      loading:         false,
      error:           '',
      verified:        false,
      verify:          {},
      couponId:        '',
      pollTimer:       null,
      pollCount:       0,
      refreshTimer:    null,
      customerId:      uni.getStorageSync('customer_id')  || '',
      tenantId:        uni.getStorageSync('tenant_id')    || '',
      tenantName:      uni.getStorageSync('tenant_name')  || '',
      // 新券到账
      preVerifyIds:     [],   // 核销前 UNUSED 券 ID 快照
      newCouponOverlay: null, // 检测到的新券数据
      couponExpired:    false // 券本身已过期（区别于验证码超时）
    }
  },
  computed: {
    displayCode() {
      return this.verify.verify_code || this.verify.static_code || this.verify.code || ''
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
    this._loadCache()
  },
  onShow()   { this.loadCode() },
  onHide()   { this.stopPolling(); this.stopRefresh() },
  onUnload() { this.stopPolling(); this.stopRefresh() },

  methods: {
    _cacheKey() { return CACHE_PREFIX + (this.couponId || 'member') },

    _loadCache() {
      try {
        const raw = uni.getStorageSync(this._cacheKey())
        if (!raw) return
        const data = JSON.parse(raw)
        if (data && Date.now() - (data._ts || 0) <= CACHE_MAX_AGE) {
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

    _isOnline() {
      return new Promise((resolve) => {
        uni.getNetworkType({
          success: ({ networkType }) => resolve(networkType !== 'none'),
          fail: () => resolve(true)
        })
      })
    },

    // ── 核销前：静默记录当前 UNUSED 券 ID 快照 ──────────────────────
    async _recordPreVerifySnapshot() {
      try {
        const res = await getCustomerCoupons('UNUSED')
        // 兼容多种响应结构
        const raw = res?.data ?? res ?? []
        const list = Array.isArray(raw)
          ? raw
          : (raw.items || raw.results || raw.list || [])
        this.preVerifyIds = list.map(c => String(c.id || ''))
      } catch (_) {
        this.preVerifyIds = []
      }
    },

    // ── 核销后：等待后端发券，拉取新券列表并 diff ─────────────────────
    async _fetchAndShowNewCoupon() {
      // 等待后端异步发券（通常在 200ms 内完成，给 1.5s 余量）
      await new Promise(resolve => setTimeout(resolve, 1500))
      try {
        const res = await getCustomerCoupons('UNUSED')
        const raw = res?.data ?? res ?? []
        const list = Array.isArray(raw)
          ? raw
          : (raw.items || raw.results || raw.list || [])

        // 找出快照里不存在的新券（即核销后新发的）
        const newCoupon = list.find(c => !this.preVerifyIds.includes(String(c.id || '')))
        if (!newCoupon) return

        // 格式化金额
        const amount   = Number(newCoupon.value ?? newCoupon.amount ?? 0)
        const minAmt   = Number(newCoupon.min_amount ?? 0)
        const amtStr   = amount.toFixed(2)
        const [intPart, decPart] = amtStr.split('.')

        // 格式化有效期
        let expireText = '长期有效'
        const expireRaw = newCoupon.expire_time || newCoupon.expired_at || newCoupon.end_time || ''
        if (expireRaw) {
          const d = new Date(expireRaw)
          if (!isNaN(d.getTime())) {
            const y = d.getFullYear()
            const m = String(d.getMonth() + 1).padStart(2, '0')
            const day = String(d.getDate()).padStart(2, '0')
            expireText = `有效期至 ${y}.${m}.${day}`
          }
        }

        this.newCouponOverlay = {
          id:         String(newCoupon.id || ''),
          name:       newCoupon.name || newCoupon.template_name || '优惠券',
          amountInt:  intPart,
          amountDec:  decPart === '00' ? '' : decPart,
          minText:    minAmt > 0 ? `满¥${minAmt}可用` : '无门槛使用',
          expireText,
        }
        // 震动庆祝
        try { uni.vibrateLong() } catch (_) {}
        setTimeout(() => { try { uni.vibrateShort() } catch (_) {} }, 600)
      } catch (_) {
        // 发券检测失败不影响主流程
      }
    },

    async loadCode() {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/mine/mine' })
        return
      }
      if (!this.couponId) {
        this.error = '请先从券包中选择一张优惠券，再点击「出示二维码」核销'
        return
      }
      const online = await this._isOnline()
      if (!online) {
        if (!this.verify.code) this.error = '当前网络不可用，请检查网络后重试'
        return
      }

      this.loading       = true
      this.error         = ''
      this.verified      = false
      this.couponExpired = false
      this.pollCount     = 0
      this.stopPolling()
      this.stopRefresh()

      try {
        const res = await getCouponVerifyCode(this.couponId)
        if (res.code !== 200 || !res.data?.code) {
          const msgLower = String(res.msg || '').toLowerCase()
          const isExpired = msgLower.includes('过期') || msgLower.includes('expired')
          const used = await this.checkCouponStatus(true)
          if (!used) {
            this.error = res.msg || '核销码生成失败'
            this.couponExpired = isExpired
          }
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
        // 静默记录快照（不阻塞主流程）
        this._recordPreVerifySnapshot()
      } catch (err) {
        const msgLower = String(err.message || '').toLowerCase()
        const isExpired = msgLower.includes('过期') || msgLower.includes('expired')
        const used = await this.checkCouponStatus(true)
        if (!used) {
          this.error = err.message || '核销码生成失败'
          this.couponExpired = isExpired
        }
      } finally {
        this.loading = false
      }
    },

    drawQr() {
      if (!this.displayCode) return
      drawQrCode({ canvasId: 'couponQrCanvas', text: this.displayCode, size: 230, context: this })
    },

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
        const status = String(res?.data?.status || '').toUpperCase()
        if (status === 'USED') {
          this.markVerified(doToast)
          return true
        }
        if (status === 'EXPIRED') {
          // 券已过期，停止轮询，显示专属提示
          this.couponExpired = true
          this.error = '这张券已过期，无法使用'
          this.stopPolling()
          this.stopRefresh()
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
      try { uni.vibrateLong() } catch (_) {}
      if (doToast) uni.showToast({ title: '核销成功', icon: 'success' })
      // 异步检测新券，不阻塞成功页面显示
      this._fetchAndShowNewCoupon()
    },

    dismissNewCoupon() {
      this.newCouponOverlay = null
    },

    goUseCoupon() {
      this.newCouponOverlay = null
      uni.redirectTo({ url: '/subpkg-coupon/pages/list' })
    },

    goCoupons() { uni.redirectTo({ url: '/subpkg-coupon/pages/list' }) },
    goHome()    { uni.reLaunch({ url: '/pages/mine/mine' }) }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 24rpx;
  background: #F7F8FA;
}

/* ── 骨架屏 ──────────────────────────────── */
.skeleton-card { margin-top: 24rpx; }
.sk {
  background: #e8e8e8;
  border-radius: 12rpx;
  animation: shimmer 1.4s ease-in-out infinite;
}
@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}
.sk-title { height: 44rpx; width: 60%; margin: 0 auto 16rpx; }
.sk-desc  { height: 30rpx; width: 80%; margin: 0 auto 36rpx; }
.sk-qr    { width: 540rpx; height: 540rpx; border-radius: 24rpx; margin: 0 auto 32rpx; }
.sk-code-area { padding: 24rpx; border-radius: 20rpx; background: #F7F8FA; }
.sk-label { height: 24rpx; width: 70%; margin-bottom: 18rpx; }
.sk-code  { height: 72rpx; width: 55%; margin: 0 auto; }

/* ── 通用卡片 ─────────────────────────────── */
.card {
  padding: 40rpx 32rpx;
  background: #fff;
  border-radius: 32rpx;
  box-shadow: 0 2rpx 16rpx rgba(0, 0, 0, 0.06);
  text-align: center;
}
.state-card   { margin-top: 120rpx; }
.success-card { border: 2rpx solid #b7ebd0; }

/* ── 核销成功 ─────────────────────────────── */
.success-ring {
  width: 120rpx;
  height: 120rpx;
  margin: 0 auto 28rpx;
  border-radius: 50%;
  background: #07C160;
  display: flex;
  align-items: center;
  justify-content: center;
}
.success-check  { display: block; color: #fff; font-size: 72rpx; font-weight: bold; line-height: 1; }
.success-amount { display: block; margin-top: 16rpx; color: #07C160; font-size: 60rpx; font-weight: bold; }
.success-member { display: block; margin-top: 8rpx; color: #999; font-size: 28rpx; }

/* ── 状态文字 ─────────────────────────────── */
.state-title { display: block; color: #111; font-size: 36rpx; font-weight: bold; }
.state-desc  { display: block; margin-top: 16rpx; color: #666; font-size: 28rpx; line-height: 1.6; }

/* ── 备用短码 ─────────────────────────────── */
.fallback-box { margin: 24rpx 0; padding: 24rpx; background: #F7F8FA; border-radius: 20rpx; }
.fallback-code { display: block; color: #07C160; font-size: 72rpx; font-weight: bold; letter-spacing: 10rpx; word-break: normal; }

/* ── 二维码区 ─────────────────────────────── */
.qr-title { display: block; color: #111; font-size: 40rpx; font-weight: bold; }
.qr-desc  { display: block; margin-top: 12rpx; color: #666; font-size: 26rpx; line-height: 1.6; }
.qr-box {
  position: relative;
  width: 540rpx; height: 540rpx;
  margin: 24rpx auto;
  display: flex; align-items: center; justify-content: center;
  border: 10rpx solid #07C160;
  border-radius: 24rpx;
  background: #fff;
  overflow: hidden;
}
.qr-refresh-mask {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 18rpx;
}
.loading-ring-sm {
  width: 56rpx; height: 56rpx;
  border: 6rpx solid #e8e8e8;
  border-top-color: #07C160;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.qr-canvas { width: 230px; height: 230px; display: block; }

/* ── 券信息栏 ─────────────────────────────── */
.coupon-info-bar { margin-bottom: 8rpx; }
.cib-name  { display: block; color: #111; font-size: 32rpx; font-weight: 600; }
.cib-value { display: block; margin-top: 8rpx; color: #07C160; font-size: 28rpx; font-weight: 600; }

/* ── 短券码 ──────────────────────────────── */
.code-box { padding: 24rpx; background: #F7F8FA; border-radius: 20rpx; margin-bottom: 24rpx; }
.code-label { display: block; color: #999; font-size: 24rpx; }
.short-code { display: block; margin-top: 12rpx; color: #111; font-size: 72rpx; font-weight: bold; letter-spacing: 10rpx; word-break: normal; }

/* ── 会员信息 ─────────────────────────────── */
.member-info { margin-top: 8rpx; }
.mi-text { display: block; color: #999; font-size: 24rpx; line-height: 1.8; }

/* ── 按钮 ────────────────────────────────── */
.btn-primary {
  display: block; width: 100%; height: 96rpx; line-height: 96rpx;
  background: #07C160; color: #fff;
  font-size: 34rpx; font-weight: 600; text-align: center;
  border-radius: 24rpx; border: none; padding: 0; box-sizing: border-box;
  &::after { border: none; }
}
.btn-plain {
  display: block; width: 100%; height: 88rpx; line-height: 88rpx;
  background: #F7F8FA; color: #333;
  font-size: 32rpx; font-weight: 500; text-align: center;
  border-radius: 24rpx; border: 2rpx solid #e8e8e8; padding: 0; box-sizing: border-box;
  &::after { border: none; }
}
.mt32 { margin-top: 32rpx; }
.mt16 { margin-top: 16rpx; }

/* ═══════════════════════════════════════════
   新券到账 庆祝遮罩
   ═══════════════════════════════════════════ */
.nc-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40rpx 32rpx;
  background: rgba(10, 4, 20, 0.80);
  /* 入场动画 */
  animation: nc-bg-in 0.3s ease;
}
@keyframes nc-bg-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* ── 彩带粒子 ── */
.confetti {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.confetti-item {
  position: absolute;
  top: -40rpx;
  width: 16rpx;
  height: 28rpx;
  border-radius: 4rpx;
  opacity: 0;
  animation: confetti-fall 2.4s ease-in forwards;
}
/* 12 粒彩带，各自颜色和位置 */
.ci-1  { left: 8%;   background: #FF6B6B; animation-delay: 0.1s; transform: rotate(20deg); }
.ci-2  { left: 18%;  background: #FFD93D; animation-delay: 0.25s; transform: rotate(-15deg); }
.ci-3  { left: 30%;  background: #6BCB77; animation-delay: 0.05s; transform: rotate(35deg); }
.ci-4  { left: 42%;  background: #4D96FF; animation-delay: 0.35s; transform: rotate(-30deg); }
.ci-5  { left: 55%;  background: #FF6B6B; animation-delay: 0.15s; transform: rotate(10deg); }
.ci-6  { left: 66%;  background: #C77DFF; animation-delay: 0.28s; transform: rotate(-20deg); }
.ci-7  { left: 76%;  background: #FFD93D; animation-delay: 0.08s; transform: rotate(40deg); }
.ci-8  { left: 88%;  background: #6BCB77; animation-delay: 0.42s; transform: rotate(-5deg); }
.ci-9  { left: 12%;  background: #4D96FF; animation-delay: 0.55s; transform: rotate(25deg); }
.ci-10 { left: 38%;  background: #FF6B6B; animation-delay: 0.60s; transform: rotate(-40deg); }
.ci-11 { left: 62%;  background: #C77DFF; animation-delay: 0.45s; transform: rotate(15deg); }
.ci-12 { left: 82%;  background: #FFD93D; animation-delay: 0.70s; transform: rotate(-25deg); }

@keyframes confetti-fall {
  0%   { opacity: 1; transform: translateY(0)      rotate(0deg);   }
  100% { opacity: 0; transform: translateY(1800rpx) rotate(720deg); }
}

/* ── 主卡片 ── */
.nc-card {
  position: relative;
  width: 100%;
  max-width: 640rpx;
  border-radius: 40rpx;
  background: #fff;
  overflow: hidden;
  text-align: center;
  animation: nc-card-in 0.38s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  box-shadow: 0 32rpx 80rpx rgba(0, 0, 0, 0.40);
}
@keyframes nc-card-in {
  from { opacity: 0; transform: scale(0.72) translateY(60rpx); }
  to   { opacity: 1; transform: scale(1)    translateY(0);     }
}

/* 顶部光晕 */
.nc-glow {
  display: none;
}

/* ── 标题区 ── */
.nc-header {
  padding: 48rpx 32rpx 32rpx;
}
.nc-emoji {
  display: block;
  font-size: 88rpx;
  line-height: 1;
  margin-bottom: 16rpx;
  animation: nc-emoji-bounce 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s both;
}
@keyframes nc-emoji-bounce {
  from { transform: scale(0) rotate(-20deg); }
  to   { transform: scale(1) rotate(0deg); }
}
.nc-title {
  display: block;
  font-size: 52rpx;
  font-weight: 900;
  color: #1a1a1a;
  letter-spacing: 4rpx;
}
.nc-subtitle {
  display: block;
  margin-top: 12rpx;
  font-size: 26rpx;
  color: #888;
}

/* ── 券体 ── */
.nc-coupon-body {
  position: relative;
  margin: 0 32rpx 32rpx;
  display: flex;
  align-items: center;
  border-radius: 24rpx;
  overflow: visible;
  background: #07C160;
  box-shadow: 0 8rpx 32rpx rgba(7, 193, 96, 0.35);
  min-height: 180rpx;
}

/* 锯齿凹凸边（模拟票券效果） */
.nc-serration {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 32rpx;
  height: 32rpx;
  border-radius: 50%;
  background: #fff;
  z-index: 2;
}
.nc-serration-left  { left:  -16rpx; }
.nc-serration-right { right: -16rpx; }

/* 左侧：金额 */
.nc-coupon-left {
  flex: 0 0 220rpx;
  padding: 28rpx 20rpx;
  text-align: center;
}
.nc-amount {
  display: block;
  color: #fff;
  font-size: 88rpx;
  font-weight: 900;
  line-height: 1;
}
.nc-amount-sign {
  font-size: 40rpx;
  vertical-align: top;
  margin-top: 14rpx;
  display: inline-block;
}
.nc-amount-dec {
  font-size: 40rpx;
  vertical-align: bottom;
  margin-bottom: 8rpx;
  display: inline-block;
}
.nc-min {
  display: block;
  margin-top: 10rpx;
  color: rgba(255, 255, 255, 0.75);
  font-size: 22rpx;
}

/* 中间分割线 */
.nc-divider {
  width: 2rpx;
  height: 120rpx;
  background: repeating-linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0.5) 0,
    rgba(255, 255, 255, 0.5) 10rpx,
    transparent 10rpx,
    transparent 20rpx
  );
  flex-shrink: 0;
}

/* 右侧：券名 + 有效期 */
.nc-coupon-right {
  flex: 1;
  padding: 28rpx 24rpx;
  text-align: left;
}
.nc-coupon-name {
  display: block;
  color: #fff;
  font-size: 30rpx;
  font-weight: 700;
  line-height: 1.4;
}
.nc-coupon-expire {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.70);
  font-size: 22rpx;
}

/* ── 操作按钮 ── */
.nc-btn-primary {
  display: block;
  width: calc(100% - 64rpx);
  margin: 0 32rpx 20rpx;
  height: 96rpx;
  line-height: 96rpx;
  background: #07C160;
  color: #fff;
  font-size: 34rpx;
  font-weight: 800;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;
  box-shadow: 0 8rpx 24rpx rgba(7, 193, 96, 0.30);
  &::after { border: none; }
}
.nc-btn-plain {
  display: block;
  width: calc(100% - 64rpx);
  margin: 0 32rpx 40rpx;
  height: 80rpx;
  line-height: 80rpx;
  background: transparent;
  color: #aaa;
  font-size: 28rpx;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;
  &::after { border: none; }
}
</style>


