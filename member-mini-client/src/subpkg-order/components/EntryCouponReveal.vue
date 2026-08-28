<template>
  <base-overlay v-if="open" layer="blocking-top" @mask-click="$emit('close')">
    <view class="ecr-wrap">
      <view class="ecr-card" :class="{ 'ecr-card--jackpot': isJackpot }">
        <text class="ecr-ribbon">{{ name || '今日专享券' }}</text>
        <view class="ecr-amount-row">
          <text class="ecr-currency">¥</text>
          <text class="ecr-amount">{{ amountText }}</text>
        </view>
        <text class="ecr-cond">{{ condText }}</text>
        <view class="ecr-dash"></view>
        <text class="ecr-valid">今日有效</text>
        <view class="ecr-btn" @click="$emit('close')"><text>收下</text></view>
      </view>
    </view>
  </base-overlay>
</template>

<script>
import BaseOverlay from '@/components/base-overlay/base-overlay.vue'

// 进店券开奖层：扫码进店抽到的那张券当场亮出来（盲盒三档 加菜小券 / 手气不错 /
// 手气爆棚 …）。纯展示，无业务逻辑；点"收下"或点遮罩都只 emit close。
// 抽到"手气爆棚"走金色描边，其余走常规红。文案只放数据，不写解释句。
export default {
  name: 'EntryCouponReveal',
  components: { BaseOverlay },
  props: {
    open: { type: Boolean, default: false },
    name: { type: String, default: '' },
    amount: { type: [Number, String], default: 0 },
    threshold: { type: [Number, String], default: 0 },
    formatPrice: { type: Function, required: true },
  },
  emits: ['close'],
  computed: {
    isJackpot() {
      return this.name === '手气爆棚'
    },
    amountText() {
      return this.formatPrice(Number(this.amount) || 0)
    },
    condText() {
      const t = Number(this.threshold) || 0
      return t > 0 ? `满${t.toFixed(0)}可用` : '无门槛'
    },
  },
}
</script>

<style lang="scss">
.ecr-wrap {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 96rpx;
}

.ecr-card {
  width: 100%;
  max-width: 480rpx;
  box-sizing: border-box;
  padding: 40rpx 36rpx 32rpx;
  border-radius: 28rpx;
  background: linear-gradient(165deg, #ff5a3c 0%, #ff2f1f 60%, #d81717 100%);
  border: 2rpx solid rgba(255, 224, 158, 0.85);
  box-shadow: 0 18rpx 44rpx -16rpx rgba(180, 20, 10, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  animation: ecr-in 0.42s cubic-bezier(0.22, 1.3, 0.4, 1) both;
}

.ecr-card--jackpot {
  background: linear-gradient(165deg, #ffb64a 0%, #ff7a1f 55%, #e0500c 100%);
  border-color: #fff0c6;
  box-shadow: 0 18rpx 48rpx -14rpx rgba(200, 110, 10, 0.55);
}

.ecr-ribbon {
  display: inline-block;
  padding: 6rpx 22rpx;
  border-radius: 999rpx;
  background: rgba(255, 255, 255, 0.2);
  color: #ffe9c2;
  font-size: 24rpx;
  font-weight: 800;
  letter-spacing: 1rpx;
}

.ecr-amount-row {
  display: flex;
  align-items: baseline;
  margin-top: 24rpx;
}

.ecr-currency {
  font-size: 36rpx;
  font-weight: 800;
  color: #fff;
  margin-right: 4rpx;
}

.ecr-amount {
  font-size: 96rpx;
  font-weight: 900;
  color: #fff;
  line-height: 1;
  text-shadow: 0 3rpx 0 rgba(120, 10, 0, 0.35);
}

.ecr-cond {
  margin-top: 10rpx;
  font-size: 25rpx;
  color: #ffe4d2;
}

.ecr-dash {
  width: 100%;
  height: 0;
  border-top: 2rpx dashed rgba(255, 255, 255, 0.35);
  margin: 24rpx 0 16rpx;
}

.ecr-valid {
  font-size: 23rpx;
  color: rgba(255, 255, 255, 0.8);
}

.ecr-btn {
  width: 100%;
  height: 84rpx;
  margin-top: 26rpx;
  border-radius: 999rpx;
  background: linear-gradient(180deg, #ffe9a8, #ffcf5c);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 10rpx 22rpx -10rpx rgba(255, 180, 40, 0.7);

  text {
    color: #7a1f00;
    font-size: 30rpx;
    font-weight: 900;
    letter-spacing: 2rpx;
  }
}

@keyframes ecr-in {
  from { transform: scale(0.82); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
</style>
