<template>
  <view class="page">
    <view class="card">
      <text class="title">会员活动</text>
      <text class="desc">当前版本先专注入会、发券和核销。活动功能后续开放。</text>
      <button class="btn" @click="goHome">回到会员中心</button>
    </view>
  </view>
</template>

<script>
export default {
  methods: {
    goHome() {
      uni.reLaunch({ url: '/pages/index/index' })
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
  background: #fff;
  border-radius: 20rpx;
  text-align: center;
}

.title,
.desc {
  display: block;
}

.title {
  color: #111827;
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
  color: #fff;
  font-size: 30rpx;
  font-weight: 700;
}
</style>
