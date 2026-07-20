<template>
  <view class="page">
    <view class="card">
      <text class="title">积分暂未开放</text>
      <text class="desc">当前版本先使用优惠券，后续再开放积分和等级权益。</text>
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


