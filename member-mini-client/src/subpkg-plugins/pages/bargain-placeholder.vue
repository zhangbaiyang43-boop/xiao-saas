<template>
  <view class="page">
    <view class="card">
      <text class="title">活动暂未开放</text>
      <text class="desc">当前先使用会员优惠券，到店核销即可享受优惠。</text>
      <button class="btn" @click="goHome">回到我的</button>
    </view>
  </view>
</template>

<script>
export default {
  methods: {
    goHome() {
      uni.reLaunch({ url: '/pages/mine/mine' })
    }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 32rpx;
  background: #f5f7fb;
}

.card {
  margin-top: 120rpx;
  padding: 42rpx 34rpx;
  background: var(--bg-card);
  border-radius: 20rpx;
  text-align: center;
}

.title,
.desc {
  display: block;
}

.title {
  color: var(--text-1);
  font-size: 40rpx;
  font-weight: 800;
}

.desc {
  margin-top: 18rpx;
  color: #64748b;
  font-size: 28rpx;
  line-height: 1.6;
}

.btn {
  width: 100%;
  height: 92rpx;
  margin-top: 34rpx;
  border-radius: 14rpx;
  background: #2563eb;
  color: var(--text-inverse);
  font-size: 30rpx;
  font-weight: 700;
}
</style>


