<template>
  <view class="page">
    <view class="hero">
      <view class="store-logo">店</view>
      <text class="store-name">{{ tenant.name || '门店会员' }}</text>
      <text class="title">扫码成为会员</text>
      <text class="subtitle">输入手机号，立即成为本店会员并领取优惠券。</text>
    </view>

    <view v-if="loading" class="card state-card">
      <view class="spinner"></view>
      <text class="state-title">{{ loadingText }}</text>
      <text class="state-desc">请稍等一下</text>
    </view>

    <view v-else-if="error" class="card state-card">
      <text class="state-icon">!</text>
      <text class="state-title">{{ error }}</text>
      <text class="state-desc">请重新扫码，或让店员帮你处理。</text>
      <button class="primary-btn" @click="reloadEntrance">重新识别</button>
      <button class="plain-btn" @click="goHome">回到会员中心</button>
    </view>

    <view v-else class="card">
      <view class="source-badge">{{ inviteCode ? '好友邀请' : `来源：${entrance.name || '门店扫码'}` }}</view>

      <view class="form-group">
        <text class="field-label">手机号</text>
        <input class="input" v-model="form.phone" placeholder="请输入 11 位手机号" type="number" maxlength="11" />
      </view>

      <view class="agreement-row" @click="agreementAccepted = !agreementAccepted">
        <view :class="['check-box', agreementAccepted ? 'checked' : '']">✓</view>
        <text>已阅读并同意</text>
        <text class="agreement-link" @click.stop="showAgreement">注册协议</text>
      </view>

      <button class="phone-login-btn" open-type="getPhoneNumber" :disabled="submitting" @getphonenumber="handlePhoneLogin">
        手机号快速登录
      </button>

      <button class="primary-btn" :loading="submitting" :disabled="submitting" @click="joinMember">
        {{ submitting ? '正在入会...' : '立即入会领券' }}
      </button>

      <text class="safe-tip">手机号只用于本店会员识别和优惠提醒。</text>
    </view>
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { joinByEntranceCode, resolveEntranceCode } from '@/api/auth'
import { saveCustomerSession } from '@/utils/auth'

const phoneReg = /^1[3-9]\d{9}$/

const wxLogin = () => {
  return new Promise((resolve, reject) => {
    uni.login({
      provider: 'weixin',
      success: (res) => {
        if (res.code) resolve(res.code)
        else reject(new Error('微信登录失败，请再试一次'))
      },
      fail: () => reject(new Error('微信登录失败，请检查小程序环境'))
    })
  })
}

const friendlyJoinMessage = (message) => {
  const text = String(message || '')
  if (!text) return '入会失败，请稍后再试'
  if (text.includes('Customer') || text.includes('Traceback') || text.includes('object')) return '门店系统正在忙，请稍后再试'
  return text
}

export default {
  setup() {
    const loading = ref(false)
    const submitting = ref(false)
    const error = ref('')
    const scene = ref('')
    const tenantId = ref('')
    const inviteCode = ref('')
    const tenant = ref({})
    const entrance = ref({})
    const form = ref({ phone: '' })
    const step = ref('recognize')
    const agreementAccepted = ref(false)

    const loadingText = computed(() => {
      if (step.value === 'join') return '正在微信登录'
      return '正在识别门店'
    })

    const parseOptions = (options = {}) => {
      const rawScene = options.scene ? decodeURIComponent(options.scene).trim() : ''
      const rawTenantId = options.tenant_id ? decodeURIComponent(options.tenant_id).trim() : ''
      const rawInviteCode = options.invite_code ? decodeURIComponent(options.invite_code).trim() : ''
      if (options.q) {
        const decoded = decodeURIComponent(options.q)
        const sceneMatch = decoded.match(/[?&]scene=([^&]+)/)
        const tenantMatch = decoded.match(/[?&]tenant_id=([^&]+)/)
        const inviteMatch = decoded.match(/[?&]invite_code=([^&]+)/)
        return {
          scene: sceneMatch ? decodeURIComponent(sceneMatch[1]).trim() : rawScene,
          tenant_id: tenantMatch ? decodeURIComponent(tenantMatch[1]).trim() : rawTenantId,
          invite_code: inviteMatch ? decodeURIComponent(inviteMatch[1]).trim() : rawInviteCode
        }
      }
      return {
        scene: rawScene || uni.getStorageSync('entrance_scene') || '',
        tenant_id: rawTenantId || uni.getStorageSync('tenant_id') || '',
        invite_code: rawInviteCode
      }
    }

    const loadEntrance = async (options = {}) => {
      const parsed = parseOptions(options)
      scene.value = parsed.scene
      tenantId.value = parsed.tenant_id
      inviteCode.value = parsed.invite_code

      if (!scene.value && !tenantId.value) {
        error.value = '没有识别到入会入口'
        return
      }

      loading.value = true
      error.value = ''
      step.value = 'recognize'

      try {
        if (scene.value) {
          const res = await resolveEntranceCode(scene.value)
          if (res.code !== 200) {
            error.value = res.msg || '入口码不可用'
            return
          }
          tenant.value = res.data?.tenant || {}
          entrance.value = res.data?.entrance || {}
          tenantId.value = tenant.value.tenant_id || tenantId.value
          uni.setStorageSync('entrance_scene', scene.value)
        } else {
          tenant.value = { tenant_id: tenantId.value, name: '门店会员' }
          entrance.value = { name: '好友邀请' }
        }
        uni.setStorageSync('tenant_id', tenantId.value)
        uni.setStorageSync('tenant_name', tenant.value.name || '')
      } catch (err) {
        error.value = err.message || '入口识别失败'
      } finally {
        loading.value = false
      }
    }

    const joinMember = async (joinOptions = {}) => {
      if (submitting.value) return
      const phone = form.value.phone.trim()
      const phoneCode = joinOptions.phoneCode || ''

      if (!scene.value && !tenantId.value) {
        uni.showToast({ title: '请重新扫码', icon: 'none' })
        return
      }
      if (!agreementAccepted.value) {
        uni.showToast({ title: '请先勾选注册协议', icon: 'none' })
        return
      }
      if (!phoneCode && !phoneReg.test(phone)) {
        uni.showToast({ title: '请输入正确手机号', icon: 'none' })
        return
      }

      submitting.value = true
      step.value = 'join'

      try {
        const code = await wxLogin()
        const res = await joinByEntranceCode({
          scene: scene.value,
          tenant_id: tenantId.value,
          invite_code: inviteCode.value,
          code,
          phone,
          phone_code: phoneCode,
          agreement_accepted: true
        })

        if (res.code === 200) {
          saveCustomerSession(res.data)
          uni.setStorageSync('coupon_modal_shown', 'false')
          uni.showToast({
            title: res.data?.is_new_customer ? '入会成功，新人券已到账' : '欢迎回来',
            icon: 'success',
            duration: 1800
          })
          setTimeout(() => {
            uni.reLaunch({ url: '/pages/index/index' })
          }, 900)
          return
        }

        uni.showToast({ title: friendlyJoinMessage(res.msg), icon: 'none' })
      } catch (err) {
        uni.showToast({ title: friendlyJoinMessage(err.message), icon: 'none' })
      } finally {
        submitting.value = false
      }
    }

    const handlePhoneLogin = (event) => {
      const phoneCode = event?.detail?.code
      if (!phoneCode) {
        uni.showToast({ title: '未获取到手机号，请手动输入', icon: 'none' })
        return
      }
      joinMember({ phoneCode })
    }

    const showAgreement = () => {
      uni.showModal({
        title: '注册协议',
        content: '成为本店会员后，手机号仅用于会员身份识别、优惠券领取、核销和到店消费提醒。我们不会把你的手机号提供给无关第三方。',
        showCancel: false,
        confirmText: '我知道了'
      })
    }

    const reloadEntrance = () => loadEntrance({ scene: scene.value, tenant_id: tenantId.value, invite_code: inviteCode.value })
    const goHome = () => uni.reLaunch({ url: '/pages/index/index' })

    return {
      loading,
      submitting,
      error,
      tenant,
      entrance,
      inviteCode,
      form,
      agreementAccepted,
      loadingText,
      loadEntrance,
      joinMember,
      handlePhoneLogin,
      showAgreement,
      reloadEntrance,
      goHome
    }
  },
  onLoad(options) {
    this.loadEntrance(options)
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 32rpx;
  background: linear-gradient(180deg, #eef6ff 0%, #f6f8fc 52%, #f6f8fc 100%);
}

.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48rpx 0 28rpx;
  text-align: center;
}

.store-logo {
  width: 112rpx;
  height: 112rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 56rpx;
  color: #2563eb;
  font-size: 36rpx;
  font-weight: 700;
  box-shadow: 0 8rpx 28rpx rgba(37, 99, 235, 0.14);
}

.store-name {
  margin-top: 24rpx;
  color: #1f2937;
  font-size: 34rpx;
  font-weight: 700;
}

.title {
  margin-top: 14rpx;
  color: #101827;
  font-size: 50rpx;
  font-weight: 800;
}

.subtitle {
  margin-top: 12rpx;
  color: #64748b;
  font-size: 28rpx;
}

.card {
  padding: 36rpx;
  background: #fff;
  border-radius: 20rpx;
  box-shadow: 0 8rpx 28rpx rgba(15, 23, 42, 0.06);
}

.source-badge {
  display: inline-flex;
  padding: 12rpx 22rpx;
  margin-bottom: 30rpx;
  border-radius: 999rpx;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 26rpx;
  font-weight: 600;
}

.form-group {
  margin-bottom: 28rpx;
}

.field-label {
  display: block;
  margin-bottom: 12rpx;
  color: #334155;
  font-size: 30rpx;
  font-weight: 600;
}

.input {
  height: 96rpx;
  padding: 0 28rpx;
  border: 2rpx solid #e5e7eb;
  border-radius: 14rpx;
  background: #f8fafc;
  font-size: 32rpx;
}

.primary-btn,
.phone-login-btn,
.plain-btn {
  width: 100%;
  height: 96rpx;
  border-radius: 14rpx;
  font-size: 32rpx;
  font-weight: 700;
}

.primary-btn {
  margin-top: 8rpx;
  background: #2563eb;
  color: #fff;
}

.phone-login-btn {
  margin-top: 18rpx;
  background: #16a34a;
  color: #fff;
}

.agreement-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  margin: 6rpx 0 12rpx;
  color: #64748b;
  font-size: 24rpx;
}

.check-box {
  width: 30rpx;
  height: 30rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2rpx solid #cbd5e1;
  border-radius: 8rpx;
  color: transparent;
  font-size: 22rpx;
}

.check-box.checked {
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}

.agreement-link {
  color: #2563eb;
  font-weight: 700;
}

.plain-btn {
  margin-top: 16rpx;
  background: #f1f5f9;
  color: #334155;
}

.safe-tip {
  display: block;
  margin-top: 22rpx;
  text-align: center;
  color: #94a3b8;
  font-size: 24rpx;
}

.state-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.state-icon {
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 36rpx;
  background: #fee2e2;
  color: #dc2626;
  font-size: 42rpx;
  font-weight: 800;
}

.state-title {
  margin-top: 22rpx;
  color: #111827;
  font-size: 32rpx;
  font-weight: 700;
}

.state-desc {
  margin-top: 10rpx;
  margin-bottom: 20rpx;
  color: #64748b;
  font-size: 26rpx;
}

.spinner {
  width: 58rpx;
  height: 58rpx;
  border: 6rpx solid #dbeafe;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
