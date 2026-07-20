<template>
  <view class="page">
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
          <view class="avatar-preview" @click="chooseAvatar">
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
      
      <view class="info-section">
        <text class="info-label">手机号</text>
        <text class="info-value">{{ customer.phone || '未绑定' }}</text>
        <text class="info-hint">如需更换手机号，请联系客服</text>
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
  </view>
</template>

<script>
import { ref, computed } from 'vue'
import { getMemberProfile, updateMemberProfile } from '@/api/auth'
import { formatDate } from '@/utils'

export default {
  setup() {
    const customer = ref({})
    const saving = ref(false)
    const form = ref({
      name: '',
      avatar: ''
    })
    const originalForm = ref({
      name: '',
      avatar: ''
    })

    const hasChanges = computed(() => {
      return form.value.name !== originalForm.value.name || 
             form.value.avatar !== originalForm.value.avatar
    })

    const loadProfile = async () => {
      try {
        const res = await getMemberProfile()
        if (res.code === 200) {
          customer.value = res.data || {}
          form.value.name = res.data.name || ''
          form.value.avatar = res.data.avatar || ''
          originalForm.value.name = res.data.name || ''
          originalForm.value.avatar = res.data.avatar || ''
        } else {
          uni.showToast({ title: res.msg || '加载失败', icon: 'none' })
        }
      } catch (err) {
        uni.showToast({ title: '网络异常', icon: 'none' })
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
        url: getBaseUrl() + '/v1/member/avatar',
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

    const getBaseUrl = () => {
      return import.meta.env.VITE_API_BASE_URL || 'https://your-api-domain.com'
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

    return {
      customer,
      saving,
      form,
      hasChanges,
      loadProfile,
      chooseAvatar,
      handleSave,
      goBack,
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
  background: #fff;
  border-radius: 20rpx;
  padding: 32rpx;
}

.form-title {
  font-size: 36rpx;
  font-weight: 700;
  color: #111827;
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
  border-color: #2563eb;
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
  background: #f3f4f6;
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

.info-section {
  padding: 24rpx;
  background: #f9fafb;
  border-radius: 12rpx;
  margin-bottom: 36rpx;
}

.info-label {
  display: block;
  font-size: 28rpx;
  color: #374151;
  margin-bottom: 8rpx;
  font-weight: 500;
}

.info-value {
  display: block;
  font-size: 30rpx;
  color: #111827;
  margin-bottom: 8rpx;
}

.info-hint {
  display: block;
  font-size: 24rpx;
  color: #9ca3af;
}

.actions {
  padding: 40rpx 32rpx;
}

.save-btn {
  height: 96rpx;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #fff;
  font-size: 32rpx;
  font-weight: 600;
  border-radius: 14rpx;
  margin-bottom: 24rpx;
}

.save-btn[disabled] {
  background: #d1d5db;
  color: #fff;
}

.cancel-btn {
  height: 88rpx;
  background: #fff;
  color: #6b7280;
  font-size: 30rpx;
  border-radius: 14rpx;
  border: 2rpx solid #e5e7eb;
}
</style>
