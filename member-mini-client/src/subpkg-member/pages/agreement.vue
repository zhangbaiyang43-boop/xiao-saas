<template>
  <view class="page">
    <view class="content">
      <text class="title">{{ isPrivacy ? '隐私政策' : '用户协议' }}</text>
      <text class="updated">更新日期：2025年1月1日</text>

      <template v-if="isPrivacy">
        <text class="section">一、我们收集的信息</text>
        <text class="para">我们仅收集为您提供服务所必要的信息，包括：您的手机号（用于会员身份识别）、微信 OpenID（用于登录）、消费记录（用于积分和券的发放）。</text>

        <text class="section">二、信息的使用</text>
        <text class="para">您的信息仅用于：会员身份验证、优惠券发放与核销、积分累计与查询、消费记录展示。我们不会将您的个人信息出售给任何第三方。</text>

        <text class="section">三、信息的存储与保护</text>
        <text class="para">您的数据存储在受保护的服务器中，我们采取合理的技术措施防止未经授权的访问、泄露或丢失。</text>

        <text class="section">四、您的权利</text>
        <text class="para">您可以随时联系我们删除账号及相关数据。退出登录后，您的设备上不会保留任何敏感信息。</text>

        <text class="section">五、联系我们</text>
        <text class="para">如对隐私政策有疑问，请联系门店工作人员或通过小程序内的反馈渠道与我们联系。</text>
      </template>

      <template v-else>
        <text class="section">一、服务说明</text>
        <text class="para">本小程序由门店提供，用于会员管理、餐饮点单及优惠权益发放。使用本小程序即表示您同意本协议。</text>

        <text class="section">二、会员权益</text>
        <text class="para">会员可享受消费积分、优惠券、储值余额等专属权益。权益的具体规则以页面展示为准，门店有权在合理范围内调整。</text>

        <text class="section">三、用户行为规范</text>
        <text class="para">您应保证提供的手机号真实有效。优惠券和积分不可转让，不可兑换现金，仅限本人在本门店使用。</text>

        <text class="section">四、储值说明</text>
        <text class="para">储值余额充值后不支持退款，可用于门店消费抵扣。如门店停业，请提前联系门店处理余额。</text>

        <text class="section">五、免责声明</text>
        <text class="para">因网络故障、不可抗力等原因导致的服务中断，门店不承担责任。如有争议，请与门店工作人员协商解决。</text>

        <text class="section">六、协议变更</text>
        <text class="para">门店有权修改本协议，修改后将在小程序内公示。继续使用即视为同意变更后的协议。</text>
      </template>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'

export default {
  setup() {
    const type = ref('')
    const isPrivacy = computed(() => type.value === 'privacy')
    return { isPrivacy, type }
  },
  onLoad(options) {
    this.type = options.type || 'user'
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #f5f7fb;
  padding: 28rpx 28rpx calc(60rpx + env(safe-area-inset-bottom));
}

.content {
  background: #fff;
  border-radius: 20rpx;
  padding: 36rpx 32rpx;
}

.title {
  display: block;
  font-size: 36rpx;
  font-weight: 800;
  color: #111827;
  margin-bottom: 8rpx;
}

.updated {
  display: block;
  font-size: 22rpx;
  color: #9ca3af;
  margin-bottom: 32rpx;
}

.section {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: #374151;
  margin-top: 32rpx;
  margin-bottom: 10rpx;
}

.para {
  display: block;
  font-size: 26rpx;
  color: #6b7280;
  line-height: 1.8;
}
</style>
