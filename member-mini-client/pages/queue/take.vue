<template>
  <view class="page">
    <view class="card hero-card">
      <text class="eyebrow">饭店排位</text>
      <text class="title">取号排队</text>
      <text class="desc">填写就餐人数，系统自动分配小桌、中桌或大桌号码。</text>
    </view>

    <view class="card form-card">
      <view class="field">
        <text class="label">就餐人数</text>
        <input class="input" type="number" v-model="partySize" placeholder="请输入人数" />
      </view>
      <view class="field">
        <text class="label">手机号（可选）</text>
        <input class="input" type="number" maxlength="11" v-model="phone" placeholder="方便过号联系" />
      </view>
      <view class="field">
        <text class="label">备注（可选）</text>
        <input class="input" v-model="note" maxlength="40" placeholder="例如靠窗、宝宝椅" />
      </view>
      <button class="primary-btn" :disabled="submitting" @click="submit">{{ submitting ? '取号中...' : '立即取号' }}</button>
      <text class="tip">1-2人取A号，3-4人取B号，5人以上取C号</text>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { createQueueTicket } from '@/api/queue'

export default {
  setup() {
    const tenantId = ref(uni.getStorageSync('tenant_id') || '')
    const partySize = ref('')
    const phone = ref('')
    const note = ref('')
    const submitting = ref(false)

    const unwrap = (res) => {
      if (res?.success === false) throw new Error(res.message || '取号失败')
      return res?.data || res
    }

    const submit = async () => {
      const size = Number(partySize.value || 0)
      if (!size || size < 1) {
        uni.showToast({ title: '请输入就餐人数', icon: 'none' })
        return
      }
      submitting.value = true
      try {
        const data = unwrap(await createQueueTicket({
          tenant_id: tenantId.value,
          party_size: size,
          phone: phone.value,
          note: note.value
        }))
        uni.setStorageSync('queue_ticket', JSON.stringify(data))
        // TODO: future - show coupon entry after queue ticket created
        uni.redirectTo({ url: `/pages/queue/result?id=${data.id}` })
      } catch (err) {
        uni.showToast({ title: err.message || '取号失败，请稍后再试', icon: 'none' })
      } finally {
        submitting.value = false
      }
    }

    return { tenantId, partySize, phone, note, submitting, submit }
  },
  onLoad(options) {
    if (options?.tenant_id) this.tenantId = String(options.tenant_id)
  }
}
</script>

<style lang="scss">
.page { min-height: 100vh; padding: 28rpx; background: #f5f6fa; }
.card { background: #fff; border-radius: 24rpx; box-shadow: 0 10rpx 26rpx rgba(15, 23, 42, 0.08); }
.hero-card { padding: 36rpx; background: #fff7ed; border: 2rpx solid #fed7aa; }
.eyebrow, .title, .desc, .label, .tip { display: block; }
.eyebrow { color: #f97316; font-size: 24rpx; font-weight: 900; }
.title { margin-top: 10rpx; color: #111827; font-size: 48rpx; font-weight: 900; }
.desc { margin-top: 14rpx; color: #64748b; font-size: 28rpx; line-height: 1.5; }
.form-card { margin-top: 24rpx; padding: 30rpx; }
.field { margin-bottom: 24rpx; }
.label { margin-bottom: 12rpx; color: #374151; font-size: 28rpx; font-weight: 800; }
.input { height: 92rpx; padding: 0 24rpx; border-radius: 18rpx; background: #f8fafc; color: #111827; font-size: 30rpx; }
.primary-btn { width: 100%; height: 96rpx; margin-top: 16rpx; border-radius: 999rpx; background: #ff3d2e; color: #fff; font-size: 34rpx; font-weight: 900; }
.primary-btn[disabled] { opacity: .65; }
.tip { margin-top: 20rpx; color: #9ca3af; font-size: 24rpx; text-align: center; }
</style>