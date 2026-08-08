<template>
  <view class="page">
    <view class="brand">开心点单</view>
    <view class="title">员工工作台</view>

    <view v-if="loading" class="card muted">正在确认微信身份…</view>

    <view v-else-if="error" class="card">
      <text class="err">{{ error }}</text>
      <text class="hint">请让门店老板在员工管理中生成微信绑定码</text>
      <button class="ghost" @click="startLogin">重试</button>
    </view>

    <view v-else-if="accounts.length" class="card">
      <text class="section">请选择工作门店</text>
      <button
        v-for="item in accounts"
        :key="item.account_id"
        class="shop"
        :disabled="selecting"
        @click="selectAccount(item)"
      >
        <text class="shop-name">{{ item.shop_name }}</text>
        <text class="shop-meta">{{ item.role_label }} · {{ item.staff_name }}</text>
      </button>
    </view>
  </view>
</template>

<script>
import { getStaffMiniprogramStatus, staffMpLogin, staffMpLoginSelect } from '@/api/staff'

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
      loading: true,
      selecting: false,
      error: '',
      accounts: [],
      lastCode: '',
    }
  },
  onShow() {
    this.startLogin()
  },
  methods: {
    openHandoff(h5Url) {
      if (!h5Url) {
        this.error = '登录已失效，请重试'
        return
      }
      uni.navigateTo({
        url: `/subpkg-staff/pages/staff-webview?url=${encodeURIComponent(h5Url)}`,
      })
    },
    async startLogin() {
      this.loading = true
      this.error = ''
      this.accounts = []
      try {
        const st = await getStaffMiniprogramStatus()
        if (!st?.data?.enabled) {
          this.error = '员工入口未启用'
          this.loading = false
          return
        }
        const code = await wxLogin()
        this.lastCode = code
        const res = await staffMpLogin(code)
        if (res.data?.multiple_accounts) {
          this.accounts = res.data.accounts || []
          this.loading = false
          return
        }
        this.openHandoff(res.data?.h5_url)
        this.loading = false
      } catch (e) {
        this.error = e?.message || '当前微信尚未绑定员工身份'
        this.loading = false
      }
    },
    async selectAccount(item) {
      if (this.selecting || !item?.account_id) return
      this.selecting = true
      try {
        const code = await wxLogin()
        const res = await staffMpLoginSelect({
          code,
          account_id: String(item.account_id),
        })
        this.openHandoff(res.data?.h5_url)
      } catch (e) {
        uni.showToast({ title: e?.message || '进入失败', icon: 'none' })
      } finally {
        this.selecting = false
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
  gap: 16rpx;
}
.muted { color: #94a3b8; }
.section { font-size: 28rpx; color: #64748b; margin-bottom: 8rpx; }
.shop {
  text-align: left;
  background: #f8fafc;
  border-radius: 16rpx;
  padding: 24rpx;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}
.shop-name { font-size: 32rpx; font-weight: 600; color: #0f172a; }
.shop-meta { font-size: 24rpx; color: #64748b; }
.err { font-size: 30rpx; color: #b45309; font-weight: 600; }
.hint { font-size: 24rpx; color: #94a3b8; line-height: 1.5; }
.ghost {
  margin-top: 12rpx;
  background: #e2e8f0;
  color: #334155;
  border-radius: 16rpx;
}
</style>
