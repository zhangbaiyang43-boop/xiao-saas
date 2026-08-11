<template>
  <view class="page">
    <view v-if="loading" class="state-card">
      <state-loading />
    </view>

    <view v-else-if="error" class="state-card">
      <state-error :title="error" desc="请稍后重试。" @retry="loadProfile" />
    </view>

    <template v-else>
      <view class="form-card">
        <view class="form-title">编辑资料</view>

        <view class="form-item">
          <text class="form-label">昵称</text>
          <input
            class="form-input"
            v-model="form.name"
            placeholder="请输入昵称"
            maxlength="20"
          />
        </view>

        <view class="form-item">
          <text class="form-label">头像</text>
          <view class="avatar-section">
            <view class="avatar-preview tap-shrink" @click="chooseAvatar">
              <image
                v-if="form.avatar"
                :src="form.avatar"
                class="avatar-img"
                mode="aspectFill"
              />
              <view v-else class="avatar-placeholder">
                <text class="avatar-icon">👤</text>
              </view>
            </view>
            <text class="avatar-tip">点击更换头像</text>
          </view>
        </view>

        <view class="form-item">
          <text class="form-label">手机号</text>
          <view class="phone-section">
            <text class="phone-value">{{ customer.phone || '未绑定' }}</text>
            <button class="phone-btn" @click="showPhoneModal">{{ customer.phone ? '更换手机号' : '绑定手机号' }}</button>
          </view>
        </view>

        <view class="form-item">
          <text class="form-label">注册时间</text>
          <text class="info-value">{{ formatDate(customer.created_at) }}</text>
        </view>
      </view>

      <view class="actions">
        <button
          class="save-btn"
          :loading="saving"
          :disabled="saving || !hasChanges"
          @click="handleSave"
        >
          保存修改
        </button>
        <button class="cancel-btn" @click="goBack">取消</button>
      </view>

      <!-- 手机号绑定弹窗 -->
      <view v-if="showModal" class="modal-overlay" @click="closeModal">
        <view class="modal-content" @click.stop>
          <view class="modal-header">
            <text class="modal-title">{{ tempPhone ? '更换手机号' : '绑定手机号' }}</text>
            <view class="modal-close" @click="closeModal">×</view>
          </view>

          <view class="modal-body">
            <view class="form-item">
              <text class="form-label">手机号</text>
              <input
                class="form-input"
                v-model="tempPhone"
                placeholder="请输入手机号"
                type="number"
                maxlength="11"
              />
            </view>

            <view class="form-item">
              <text class="form-label">验证码</text>
              <view class="code-section">
                <input
                  class="form-input code-input"
                  v-model="tempCode"
                  placeholder="请输入验证码"
                  type="number"
                  maxlength="6"
                />
                <button
                  class="code-btn"
                  :disabled="countdown > 0 || sendingCode"
                  @click="handleSendCode"
                >
                  {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
                </button>
              </view>
            </view>
          </view>

          <view class="modal-footer">
            <button class="modal-confirm-btn" @click="handleBindPhone">确认绑定</button>
          </view>
        </view>
      </view>
    </template>
  </view>
</template>

<script>
import { ref, computed, onUnmounted } from 'vue'
import { getMemberProfile, updateMemberProfile, sendVerifyCode, bindPhone } from '@/api/auth'
import { formatDate } from '@/utils'
import { config } from '@/config'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'

export default {
  components: { StateLoading, StateError },
  setup() {
    const customer = ref({})
    const loading = ref(true)
    const error = ref('')
    const saving = ref(false)
    const form = ref({
      name: '',
      avatar: ''
    })
    const originalForm = ref({
      name: '',
      avatar: ''
    })
    
    const showModal = ref(false)
    const tempPhone = ref('')
    const tempCode = ref('')
    const countdown = ref(0)
    const sendingCode = ref(false)
    let countdownTimer = null

    const clearCountdownTimer = () => {
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
    }

    onUnmounted(clearCountdownTimer)

    const hasChanges = computed(() => {
      return form.value.name !== originalForm.value.name || 
             form.value.avatar !== originalForm.value.avatar
    })

    const loadProfile = async () => {
      loading.value = true
      error.value = ''
      try {
        const res = await getMemberProfile()
        if (res.code === 200) {
          customer.value = res.data || {}
          form.value.name = res.data.name || ''
          form.value.avatar = res.data.avatar || ''
          originalForm.value.name = res.data.name || ''
          originalForm.value.avatar = res.data.avatar || ''
        } else {
          error.value = res.msg || '加载失败'
        }
      } catch (err) {
        error.value = '网络异常'
      } finally {
        loading.value = false
      }
    }

    const chooseAvatar = () => {
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: (res) => {
          if (res.tempFilePaths.length > 0) {
            form.value.avatar = res.tempFilePaths[0]
            uploadAvatar(res.tempFilePaths[0])
          }
        },
        fail: () => {
          uni.showToast({ title: '请选择图片', icon: 'none' })
        }
      })
    }

    const uploadAvatar = (filePath) => {
      uni.showLoading({ title: '上传中...' })
      uni.uploadFile({
        url: config.apiBaseUrl + '/v1/member/avatar',
        filePath: filePath,
        name: 'file',
        header: {
          'Authorization': 'Bearer ' + uni.getStorageSync('customer_token')
        },
        success: (uploadRes) => {
          uni.hideLoading()
          try {
            const data = JSON.parse(uploadRes.data)
            if (data.code === 200 && data.data && data.data.url) {
              form.value.avatar = data.data.url
              uni.showToast({ title: '上传成功', icon: 'success' })
            } else {
              uni.showToast({ title: data.msg || '上传失败', icon: 'none' })
            }
          } catch (e) {
            uni.showToast({ title: '上传失败', icon: 'none' })
          }
        },
        fail: () => {
          uni.hideLoading()
          uni.showToast({ title: '上传失败', icon: 'none' })
        }
      })
    }

    const handleSave = async () => {
      if (!hasChanges.value) return
      
      saving.value = true
      try {
        const updateData = {}
        if (form.value.name !== originalForm.value.name) {
          updateData.name = form.value.name.trim()
        }
        if (form.value.avatar !== originalForm.value.avatar) {
          updateData.avatar = form.value.avatar
        }
        
        const res = await updateMemberProfile(updateData)
        if (res.code === 200) {
          uni.showToast({ title: '保存成功', icon: 'success' })
          originalForm.value.name = form.value.name
          originalForm.value.avatar = form.value.avatar
          setTimeout(() => {
            uni.navigateBack()
          }, 1500)
        } else {
          uni.showToast({ title: res.msg || '保存失败', icon: 'none' })
        }
      } catch (err) {
        uni.showToast({ title: '保存失败', icon: 'none' })
      } finally {
        saving.value = false
      }
    }

    const goBack = () => {
      uni.navigateBack()
    }
    
    const showPhoneModal = () => {
      tempPhone.value = ''
      tempCode.value = ''
      showModal.value = true
    }
    
    const closeModal = () => {
      showModal.value = false
      countdown.value = 0
      clearCountdownTimer()
    }
    
    const handleSendCode = async () => {
      if (!tempPhone.value || tempPhone.value.length !== 11) {
        uni.showToast({ title: '请输入正确的手机号', icon: 'none' })
        return
      }
      
      sendingCode.value = true
      try {
        const res = await sendVerifyCode(tempPhone.value)
        if (res.code === 200) {
          uni.showToast({ title: '验证码已发送', icon: 'success' })
          countdown.value = 60
          clearCountdownTimer()
          countdownTimer = setInterval(() => {
            countdown.value--
            if (countdown.value <= 0) {
              clearCountdownTimer()
            }
          }, 1000)
        } else {
          uni.showToast({ title: res.msg || '发送失败', icon: 'none' })
        }
      } catch (err) {
        uni.showToast({ title: '发送失败', icon: 'none' })
      } finally {
        sendingCode.value = false
      }
    }
    
    const handleBindPhone = async () => {
      if (!tempPhone.value || tempPhone.value.length !== 11) {
        uni.showToast({ title: '请输入正确的手机号', icon: 'none' })
        return
      }
      if (!tempCode.value || tempCode.value.length !== 6) {
        uni.showToast({ title: '请输入6位验证码', icon: 'none' })
        return
      }
      
      try {
        const res = await bindPhone(tempPhone.value, tempCode.value)
        if (res.code === 200) {
          uni.showToast({ title: '绑定成功', icon: 'success' })
          customer.value.phone = tempPhone.value
          closeModal()
        } else {
          uni.showToast({ title: res.msg || '绑定失败', icon: 'none' })
        }
      } catch (err) {
        uni.showToast({ title: '绑定失败', icon: 'none' })
      }
    }

    return {
      customer,
      loading,
      error,
      saving,
      form,
      hasChanges,
      showModal,
      tempPhone,
      tempCode,
      countdown,
      sendingCode,
      loadProfile,
      chooseAvatar,
      handleSave,
      goBack,
      showPhoneModal,
      closeModal,
      handleSendCode,
      handleBindPhone,
      formatDate
    }
  },
  onLoad() {
    this.loadProfile()
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  padding: 24rpx;
  background: #f5f7fb;
}

.form-card {
  background: var(--bg-card);
  border-radius: 20rpx;
  padding: 32rpx;
}

.state-card {
  margin: 160rpx 32rpx 0;
  padding: 40rpx 32rpx;
  background: var(--bg-card);
  border-radius: 20rpx;
  text-align: center;
}

.form-title {
  font-size: 36rpx;
  font-weight: 700;
  color: var(--text-1);
  margin-bottom: 40rpx;
  text-align: center;
}

.form-item {
  margin-bottom: 36rpx;
}

.form-label {
  display: block;
  font-size: 28rpx;
  color: #374151;
  margin-bottom: 16rpx;
  font-weight: 500;
}

.form-input {
  height: 88rpx;
  padding: 0 24rpx;
  background: #f9fafb;
  border: 2rpx solid #e5e7eb;
  border-radius: 12rpx;
  font-size: 30rpx;
}

.form-input:focus {
  border-color: var(--brand);
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 24rpx;
}

.avatar-preview {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  overflow: hidden;
}

.avatar-img {
  width: 100%;
  height: 100%;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: var(--bg-muted);
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-icon {
  font-size: 60rpx;
}

.avatar-tip {
  font-size: 24rpx;
  color: #9ca3af;
}

.phone-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 24rpx;
  background: #f9fafb;
  border-radius: 12rpx;
}

.phone-value {
  font-size: 30rpx;
  color: var(--text-1);
}

.phone-btn {
  padding: 12rpx 24rpx;
  background: var(--brand);
  color: var(--text-inverse);
  font-size: 24rpx;
  border-radius: 8rpx;
}

.info-value {
  display: block;
  font-size: 30rpx;
  color: var(--text-1);
  padding: 20rpx 24rpx;
  background: #f9fafb;
  border-radius: 12rpx;
}

.actions {
  padding: 40rpx 32rpx;
}

.save-btn {
  height: 96rpx;
  background: var(--brand-gradient);
  color: var(--text-inverse);
  font-size: 32rpx;
  font-weight: 600;
  border-radius: 14rpx;
  margin-bottom: 24rpx;
}

.save-btn[disabled] {
  background: #d1d5db;
  color: var(--text-inverse);
}

.cancel-btn {
  height: 88rpx;
  background: var(--bg-card);
  color: var(--text-3);
  font-size: 30rpx;
  border-radius: 14rpx;
  border: 2rpx solid #e5e7eb;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--mask-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.modal-content {
  width: 600rpx;
  background: var(--bg-card);
  border-radius: 24rpx;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx;
  border-bottom: 1rpx solid #e5e7eb;
}

.modal-title {
  font-size: 32rpx;
  font-weight: 700;
  color: var(--text-1);
}

.modal-close {
  font-size: 48rpx;
  color: #9ca3af;
  line-height: 1;
}

.modal-body {
  padding: 32rpx;
}

.modal-footer {
  padding: 0 32rpx 32rpx;
}

.modal-confirm-btn {
  height: 88rpx;
  background: var(--brand-gradient);
  color: var(--text-inverse);
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 14rpx;
}

.code-section {
  display: flex;
  gap: 16rpx;
}

.code-input {
  flex: 1;
}

.code-btn {
  width: 200rpx;
  height: 88rpx;
  background: var(--brand);
  color: var(--text-inverse);
  font-size: 26rpx;
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.code-btn[disabled] {
  background: #d1d5db;
  color: var(--text-inverse);
}
</style>
