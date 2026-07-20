<template>
  <view class="page">
    <view class="header">
      <text class="balance">¥{{ balance.toFixed(2) }}</text>
      <text class="balance-label">当前储值余额</text>
    </view>

    <view class="section-title">选择充值金额</view>
    <view class="amount-grid">
      <view
        v-for="opt in amountOptions"
        :key="opt"
        :class="['amount-item', { selected: selectedAmount === opt }]"
        @click="selectedAmount = opt; customAmount = ''"
      >
        <text class="ai-main">¥{{ opt }}</text>
      </view>
    </view>

    <view class="custom-wrap">
      <text class="custom-label">其他金额</text>
      <input
        v-model="customAmount"
        class="custom-input"
        type="digit"
        placeholder="输入金额（元）"
        @focus="selectedAmount = null"
      />
    </view>

    <view class="tip">充值后可在点餐时选择余额支付，不设有效期。</view>

    <button class="pay-btn" :disabled="paying || !finalAmount" @click="doRecharge">
      {{ paying ? '处理中…' : `确认充值 ¥${finalAmount ? finalAmount.toFixed(2) : '0.00'}` }}
    </button>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { getBalance, recharge } from '@/api/auth'

export default {
  setup() {
    const balance = ref(0)
    const selectedAmount = ref(50)
    const customAmount = ref('')
    const paying = ref(false)

    const amountOptions = [30, 50, 100, 200, 500]

    const finalAmount = computed(() => {
      if (customAmount.value) {
        const v = parseFloat(customAmount.value)
        return isNaN(v) || v <= 0 ? null : v
      }
      return selectedAmount.value
    })

    const loadBalance = async () => {
      try {
        const res = await getBalance()
        if (res.code === 200) balance.value = res.data.balance ?? 0
      } catch (e) {}
    }

    const doRecharge = async () => {
      if (!finalAmount.value || paying.value) return
      paying.value = true
      try {
        const res = await recharge(finalAmount.value)
        if (res.code === 200) {
          balance.value = res.data.balance ?? balance.value
          uni.showToast({ title: `充值成功！余额 ¥${balance.value.toFixed(2)}`, icon: 'success', duration: 2000 })
          customAmount.value = ''
          selectedAmount.value = 50
        } else {
          uni.showToast({ title: res.msg || '充值失败', icon: 'none' })
        }
      } catch (e) {
        uni.showToast({ title: '网络错误，请重试', icon: 'none' })
      } finally {
        paying.value = false
      }
    }

    return { balance, selectedAmount, customAmount, amountOptions, finalAmount, paying, doRecharge, loadBalance }
  },
  onShow() { this.loadBalance() }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #f5f7fb;
  padding-bottom: 40rpx;
}

.header {
  background: #7c3aed;
  padding: 60rpx 40rpx 48rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.balance {
  font-size: 72rpx;
  font-weight: 900;
  color: #fff;
  line-height: 1;
}

.balance-label {
  margin-top: 12rpx;
  font-size: 26rpx;
  color: rgba(255,255,255,0.8);
}

.section-title {
  margin: 32rpx 28rpx 16rpx;
  font-size: 26rpx;
  color: #6b7280;
  font-weight: 600;
}

.amount-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18rpx;
  margin: 0 28rpx;
}

.amount-item {
  background: #fff;
  border-radius: 16rpx;
  padding: 28rpx 0;
  text-align: center;
  border: 2rpx solid #e5e7eb;
  transition: all 0.15s;

  &.selected {
    border-color: #7c3aed;
    background: #f3f0ff;
  }

  &:active { opacity: 0.8; }
}

.ai-main {
  display: block;
  font-size: 36rpx;
  font-weight: 800;
  color: #111827;

  .selected & { color: #7c3aed; }
}

.custom-wrap {
  margin: 20rpx 28rpx 0;
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx 28rpx;
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.custom-label {
  font-size: 26rpx;
  color: #6b7280;
  white-space: nowrap;
}

.custom-input {
  flex: 1;
  font-size: 30rpx;
  color: #111827;
  border: none;
  outline: none;
}

.tip {
  margin: 20rpx 28rpx 0;
  font-size: 22rpx;
  color: #9ca3af;
  line-height: 1.6;
}

.pay-btn {
  margin: 40rpx 28rpx 0;
  width: calc(100% - 56rpx);
  height: 96rpx;
  border-radius: 20rpx;
  font-size: 32rpx;
  font-weight: 700;
  background: #7c3aed;
  color: #fff;

  &[disabled] { background: #c4b5fd; }
}
</style>
