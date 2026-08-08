<template>
  <view class="page">
    <view class="brand">开心点单</view>
    <view class="title">正在绑定员工身份</view>

    <view v-if="loading" class="card muted">加载中…</view>
    <view v-else-if="error" class="card">
      <text class="err">{{ error }}</text>
      <text class="hint">请让老板重新生成微信绑定码</text>
    </view>
    <view v-else class="card">
      <text class="shop">{{ preview.shop_name }}</text>
      <text class="name">{{ preview.staff_name }}</text>
      <text class="role">{{ preview.role_label }}</text>
      <button class="primary" :disabled="confirming" @click="confirmBind">
        {{ confirming ? '绑定中…' : '确认绑定' }}
      </button>
      <text class="hint">仅用于识别员工工作身份</text>
    </view>
  </view>
</template>

<script>
import { confirmStaffMpBind, getStaffMiniprogramStatus, previewStaffMpBind } from '@/api/staff'
import { normalizeStaffBindScene } from '@/utils/staffBindTestScanner'

const wxLogin = () =>
  new Promise((resolve, reject) => {
    uni.login({
      provider: 'weixin',
      success: (res) => (res.code ? resolve(res.code) : reject(new Error('微信登录失败'))),
      fail: () => reject(new Error('微信登录失败')),
    })
  })

export default {
  data() {
    return {
      scene: '',
      loading: true,
      confirming: false,
      error: '',
      preview: {
        shop_name: '',
        staff_name: '',
        role_label: '',
      },
    }
  },
  onLoad(options) {
    // Official wxacode options.scene and TEMP test navigateTo ?scene= share this path.
    this.scene = normalizeStaffBindScene(options || {})
    this.loadPreview()
  },
  methods: {
    async loadPreview() {
      this.loading = true
      this.error = ''
      if (!this.scene) {
        this.error = '绑定码已失效'
        this.loading = false
        return
      }
      try {
        const st = await getStaffMiniprogramStatus()
        if (!st?.data?.enabled) {
          this.error = '员工绑定未启用'
          this.loading = false
          return
        }
        const res = await previewStaffMpBind(this.scene)
        this.preview = {
          shop_name: res.data?.shop_name || '门店',
          staff_name: res.data?.staff_name || '',
          role_label: res.data?.role_label || '',
        }
      } catch (e) {
        // bind scene 失效/无效 ≠ 顾客登录过期
        if (e?.bizCode === 'bind_expired' || /绑定码/.test(String(e?.message || ''))) {
          this.error = e?.message || '员工绑定码已过期，请让老板重新生成'
        } else {
          this.error = e?.message || '绑定码已失效'
        }
      } finally {
        this.loading = false
      }
    },
    async confirmBind() {
      if (this.confirming || !this.scene) return
      this.confirming = true
      try {
        const code = await wxLogin()
        const res = await confirmStaffMpBind({ scene: this.scene, code })
        const h5Url = res.data?.h5_url
        if (!h5Url) {
          uni.showToast({ title: '绑定成功，请从员工工作台进入', icon: 'none' })
          return
        }
        uni.redirectTo({
          url: `/subpkg-staff/pages/staff-webview?url=${encodeURIComponent(h5Url)}`,
        })
      } catch (e) {
        uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
      } finally {
        this.confirming = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding: 64rpx 40rpx;
  background: #f5f7fb;
  box-sizing: border-box;
}
.brand {
  font-size: 44rpx;
  font-weight: 700;
  color: #07c160;
}
.title {
  margin-top: 12rpx;
  font-size: 34rpx;
  color: #0f172a;
  font-weight: 600;
}
.card {
  margin-top: 40rpx;
  background: #fff;
  border-radius: 24rpx;
  padding: 40rpx 32rpx;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.muted { color: #94a3b8; }
.shop { font-size: 28rpx; color: #64748b; }
.name { font-size: 40rpx; font-weight: 700; color: #0f172a; }
.role { font-size: 28rpx; color: #334155; margin-bottom: 16rpx; }
.primary {
  margin-top: 12rpx;
  background: #07c160;
  color: #fff;
  border-radius: 16rpx;
  font-size: 32rpx;
  font-weight: 600;
}
.hint {
  margin-top: 8rpx;
  font-size: 22rpx;
  color: #94a3b8;
  text-align: center;
}
.err {
  font-size: 30rpx;
  color: #b45309;
  font-weight: 600;
}
</style>
