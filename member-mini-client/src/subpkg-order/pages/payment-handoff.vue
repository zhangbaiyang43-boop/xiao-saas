<template>
  <view class="page">
    <view class="status">
      <text class="title">{{ title }}</text>
      <text class="desc">{{ desc }}</text>
    </view>

    <view v-if="handoff" class="order-card">
      <view class="row"><text>桌号</text><text>{{ handoff.table_no || '-' }}号桌</text></view>
      <view class="row amount"><text>需支付</text><text>¥{{ amountText }}</text></view>
      <view class="items">
        <view v-for="item in handoff.items || []" :key="`${item.dish_id}-${item.name}`" class="item">
          <text>{{ item.name }} ×{{ item.qty }}</text>
          <text>¥{{ (Number(item.price || 0) * Number(item.qty || 0)).toFixed(2) }}</text>
        </view>
      </view>
    </view>

    <button class="pay-btn" :disabled="busy || paid || !handoff" @click="handlePay">
      {{ buttonText }}
    </button>
    <button v-if="error" class="plain-btn" @click="loadHandoff">重试</button>
  </view>
</template>

<script>
import { loginOrCreateMember } from '@/api/auth'
import { resolvePaymentHandoff, claimPaymentHandoff, payPaymentHandoff } from '@/api/paymentHandoff'
import { saveCustomerSession } from '@/utils/auth'

const wxLogin = () => new Promise((resolve, reject) => {
  uni.login({
    success: (res) => res.code ? resolve(res.code) : reject(new Error('微信登录失败')),
    fail: reject,
  })
})

export default {
  data() {
    return {
      token: '',
      handoff: null,
      busy: false,
      error: '',
      paid: false,
    }
  },
  computed: {
    amountText() {
      return Number(this.handoff?.amount || 0).toFixed(2)
    },
    title() {
      if (this.paid) return '支付成功'
      if (this.error) return '付款码不可用'
      return '确认加菜付款'
    },
    desc() {
      if (this.paid) return '厨房已收到这份加菜单'
      if (this.error) return this.error
      return '服务员已帮你选好菜品，确认金额后完成微信支付'
    },
    buttonText() {
      if (this.busy) return '处理中...'
      if (this.paid) return '已完成'
      return '确认并支付'
    },
  },
  async onLoad(options = {}) {
    this.token = decodeURIComponent(options.scene || options.token || '')
    await this.loadHandoff()
  },
  methods: {
    async loadHandoff() {
      if (!this.token) {
        this.error = '缺少付款码'
        return
      }
      this.busy = true
      this.error = ''
      try {
        const res = await resolvePaymentHandoff(this.token)
        const data = res?.data || res
        this.handoff = data
        this.paid = data?.status === 'PAID' || data?.payment_status === 'paid'
        if (data?.status === 'EXPIRED') this.error = '付款码已过期，请联系服务员重新生成'
      } catch (err) {
        this.error = err.message || '付款码无效'
      } finally {
        this.busy = false
      }
    },
    async ensureLogin() {
      const localTenantId = uni.getStorageSync('tenant_id')
      if (uni.getStorageSync('customer_token') && String(localTenantId || '') === String(this.handoff?.tenant_id || '')) return
      const code = await wxLogin()
      const res = await loginOrCreateMember({
        tenant_id: this.handoff?.tenant_id,
        code,
        name: '微信顾客',
      })
      const data = res?.data || res
      saveCustomerSession(data)
    },
    async handlePay() {
      if (this.busy || this.paid || !this.handoff) return
      this.busy = true
      this.error = ''
      try {
        await this.ensureLogin()
        await claimPaymentHandoff(this.token)
        const code = await wxLogin()
        const res = await payPaymentHandoff(this.token, code)
        const data = res?.data || res
        if (data?.free) {
          this.paid = true
          return
        }
        const p = data?.pay_params
        if (!p) throw new Error('支付参数生成失败')
        await uni.requestPayment({
          timeStamp: p.timeStamp,
          nonceStr: p.nonceStr,
          package: p.package,
          signType: p.signType || 'RSA',
          paySign: p.paySign,
        })
        this.paid = true
      } catch (err) {
        this.error = err?.errMsg?.includes('cancel') ? '已取消支付，可重新发起' : (err.message || '支付失败，请重试')
      } finally {
        this.busy = false
      }
    },
  },
}
</script>

<style scoped>
.page { min-height: 100vh; background: #f5f7fb; padding: 32rpx 28rpx calc(40rpx + env(safe-area-inset-bottom)); box-sizing: border-box; }
.status { padding: 28rpx 4rpx 22rpx; display: flex; flex-direction: column; gap: 10rpx; }
.title { font-size: 42rpx; font-weight: 900; color: #111827; line-height: 1.25; }
.desc { font-size: 28rpx; color: #5f6b7a; line-height: 1.45; }
.order-card { background: #fff; border-radius: 20rpx; padding: 24rpx; box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, .06); }
.row { display: flex; align-items: center; justify-content: space-between; font-size: 28rpx; color: #667085; line-height: 1.6; }
.row text:last-child { color: #111827; font-weight: 800; }
.amount { margin-top: 8rpx; }
.amount text:last-child { color: #07c160; font-size: 40rpx; font-weight: 900; }
.items { margin-top: 18rpx; border-top: 1rpx solid #eef1f5; padding-top: 12rpx; }
.item { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 10rpx 0; font-size: 26rpx; color: #344054; }
.item text:first-child { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pay-btn { margin-top: 32rpx; height: 92rpx; border-radius: 999rpx; background: #07c160; color: #fff; font-size: 32rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; }
.pay-btn[disabled] { opacity: .66; }
.pay-btn::after, .plain-btn::after { border: 0; }
.plain-btn { margin-top: 18rpx; height: 80rpx; border-radius: 999rpx; background: #fff; color: #111827; font-size: 28rpx; }
</style>
