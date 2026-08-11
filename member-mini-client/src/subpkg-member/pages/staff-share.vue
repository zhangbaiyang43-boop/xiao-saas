<template>
  <view class="page">
    <view class="hero-card">
      <text class="hc-title">{{ shopName ? `帮${shopName}带位新朋友` : '带位新朋友到店' }}</text>
      <text class="hc-desc">点右上角"转发给朋友"，朋友点开你分享的卡片，会自动和你的推荐关系绑在一起，不用再手动输入任何码。</text>
    </view>

    <view class="card invite-card">
      <text class="card-title">{{ staffName ? `${staffName} 的专属推荐` : '我的专属推荐' }}</text>
      <button class="btn-primary" open-type="share">转发给朋友</button>
      <text class="card-tip">朋友首次到店消费后，你会得到一笔佣金，由商家线下发放。</text>
      <view class="code-box-mini">
        <text class="code-mini-label">转发打不开时，可以让朋友手动输入邀请码</text>
        <text class="code-mini-val">{{ inviteCode || '-' }}</text>
      </view>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'

export default {
  setup() {
    const tenantId = ref('')
    const inviteCode = ref('')
    const staffName = ref('')
    const shopName = ref('')

    return { tenantId, inviteCode, staffName, shopName }
  },
  onLoad(options = {}) {
    // 这个页面只认自己的 URL 参数，不读、不写任何本地 storage——避免跟顾客
    // 自己被邀请时留在本机的 invite_code 混在一起，导致随手转发被错误地
    // 算成"帮邀请我的那个人扩列"。
    this.tenantId = options.tenant_id ? decodeURIComponent(options.tenant_id) : ''
    this.inviteCode = options.invite_code ? decodeURIComponent(options.invite_code) : ''
    this.staffName = options.staff_name ? decodeURIComponent(options.staff_name) : ''
    this.shopName = options.shop_name ? decodeURIComponent(options.shop_name) : ''
    uni.setNavigationBarTitle({ title: '我的推荐' })
  },
  onShareAppMessage() {
    return {
      title: this.shopName ? `${this.shopName}请你来吃饭，到店立减` : '我送你一张优惠券，到店可用',
      path: `/pages/entry/index?tenant_id=${encodeURIComponent(this.tenantId)}&invite_code=${encodeURIComponent(this.inviteCode)}`,
      imageUrl: '/static/share/invite-card.png',
    }
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #F7F8FA;
}

.hero-card {
  padding: 48rpx 32rpx 40rpx;
  background: var(--brand);
}

.hc-title {
  display: block;
  color: var(--text-inverse);
  font-size: 40rpx;
  font-weight: bold;
  line-height: 1.35;
}

.hc-desc {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.88);
  font-size: 26rpx;
  line-height: 1.6;
}

.card {
  margin: 24rpx 24rpx 0;
  padding: 32rpx;
  background: var(--bg-card);
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

.btn-primary {
  display: block;
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  background: var(--brand);
  color: var(--text-inverse);
  font-size: 34rpx;
  font-weight: 600;
  text-align: center;
  border-radius: 24rpx;
  border: none;
  padding: 0;
  box-sizing: border-box;

  &::after { border: none; }
}

.card-tip {
  display: block;
  margin-top: 16rpx;
  color: #999;
  font-size: 24rpx;
  line-height: 1.6;
}

.code-box-mini {
  margin-top: 20rpx;
  padding: 16rpx 20rpx;
  background: #F7F8FA;
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.code-mini-label {
  color: #B0B3BA;
  font-size: 20rpx;
  flex: 1;
  margin-right: 12rpx;
}

.code-mini-val {
  color: #999;
  font-size: 26rpx;
  font-weight: 600;
  letter-spacing: 2rpx;
}
</style>
