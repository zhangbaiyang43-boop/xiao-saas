<template>
  <view class="mine-page">
    <view v-if="loading" class="state-card">
      <view class="spinner"></view>
      <text class="state-title">正在加载</text>
    </view>

    <view v-else-if="error" class="state-card">
      <text class="state-title">{{ error }}</text>
      <text class="state-desc">请稍后重试。</text>
      <button class="primary-btn" @click="loadProfile">重新加载</button>
    </view>

    <view v-else class="mine-content">
      <view class="identity-card">
        <image
          v-if="isLoggedIn && customerAvatar"
          class="identity-avatar"
          :src="customerAvatar"
          mode="aspectFill"
        />
        <view v-else class="identity-avatar identity-avatar-default">
          <text>{{ isLoggedIn ? '我' : '开' }}</text>
        </view>

        <view class="identity-main">
          <text class="identity-name">{{ isLoggedIn ? displayName : '欢迎使用开心点单' }}</text>
          <text v-if="isLoggedIn && customerPhone" class="identity-phone">{{ formatPhone(customerPhone) }}</text>
          <text v-if="isLoggedIn" class="identity-bind">{{ customerPhone ? '已绑定手机号' : '未绑定手机号' }}</text>
          <text v-else class="identity-phone">登录后查看订单和账户信息</text>
        </view>

        <button v-if="isLoggedIn && !customerPhone" class="identity-sub-btn" @click="goBindPhone">去绑定</button>
        <button
          v-if="!isLoggedIn && hasStoreContext"
          class="identity-login-btn"
          open-type="getPhoneNumber"
          :disabled="authorizing"
          @getphonenumber="handleLoginAuth"
        >{{ authorizing ? '登录中…' : '微信快捷登录' }}</button>
        <button
          v-else-if="!isLoggedIn"
          class="identity-login-btn"
          :disabled="authorizing"
          @click="scanStoreCode"
        >扫码进入门店</button>
      </view>

      <view class="store-card" @click="showStoreInfo">
        <view class="store-main">
          <text class="store-label">当前门店</text>
          <text class="store-name">{{ currentStoreName }}</text>
          <text v-if="storeSceneText" class="store-scene">{{ storeSceneText }}</text>
          <text v-if="lastVisitText" class="store-visit">最近到店：{{ lastVisitText }}</text>
        </view>
        <text class="card-arrow">›</text>
      </view>

      <view v-if="isLoggedIn && recentOrder" class="recent-order-card" @click="openRecentOrder">
        <view class="section-head">
          <text class="section-title">最近订单</text>
          <text class="card-arrow">›</text>
        </view>
        <view class="order-meta">
          <text v-if="recentOrderTime">{{ recentOrderTime }}</text>
          <text v-if="recentOrderScene">{{ recentOrderScene }}</text>
        </view>
        <text class="order-summary">{{ recentOrderSummary }}</text>
        <view class="order-bottom">
          <text class="order-amount">¥{{ formatMoney(recentOrder.total) }}</text>
          <text class="order-status">{{ statusLabel(recentOrder.status) }}</text>
        </view>
      </view>

      <view class="service-card">
        <text class="service-title">服务与设置</text>
        <view class="service-list">
          <view class="service-row" @click="goOrders">
            <view class="service-icon"><text>单</text></view>
            <view class="service-copy">
              <text class="service-name">我的订单</text>
              <text class="service-desc">{{ !isLoggedIn ? '登录后查看历史订单' : (recentOrder ? '查看历史订单和消费明细' : '暂无订单记录') }}</text>
            </view>
            <text class="card-arrow">›</text>
          </view>

          <view v-if="storePhone" class="service-divider"></view>
          <view v-if="storePhone" class="service-row" @click="callStore">
            <view class="service-icon"><text>电</text></view>
            <view class="service-copy">
              <text class="service-name">联系门店</text>
              <text class="service-desc">拨打门店电话</text>
            </view>
            <text class="card-arrow">›</text>
          </view>
        </view>
      </view>

      <button v-if="isLoggedIn" class="logout-text-btn" @click="logout">退出登录</button>

      <view class="agreement-row">
        <text class="agreement-link" @click="openAgreement('user')">用户协议</text>
        <text class="agreement-sep">·</text>
        <text class="agreement-link" @click="openAgreement('privacy')">隐私政策</text>
      </view>
    </view>
  </view>
</template>

<script>
import { computed, ref } from 'vue'
import { getMemberProfile, entryJoin } from '@/api/auth'
import { clearCustomerSession, saveCustomerSession } from '@/utils/auth'
import { formatMoney, formatPhone } from '@/utils'

const wxLogin = () => new Promise((resolve, reject) => {
  uni.login({
    provider: 'weixin',
    success: (res) => res.code ? resolve(res.code) : reject(new Error('微信登录失败，请重试')),
    fail: () => reject(new Error('微信登录失败，请检查小程序环境'))
  })
})
const normalizeList = (value) => {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.items)) return value.items
  if (Array.isArray(value?.list)) return value.list
  if (Array.isArray(value?.records)) return value.records
  return []
}

const formatShortDate = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

const formatOrderTime = (value) => {
  if (!value) return ''
  if (typeof value === 'string' && /^\d{2}:\d{2}$/.test(value)) return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value || '')
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

export default {
  setup() {
    const customer = ref({})
    const loading = ref(false)
    const error = ref('')
    const isLoggedIn = ref(false)
    const recentOrder = ref(null)
    const authorizing = ref(false)

    const currentStoreName = computed(() =>
      customer.value.tenant_name ||
      customer.value.shop_name ||
      uni.getStorageSync('tenant_name') ||
      '未识别门店'
    )

    const hasStoreContext = computed(() => Boolean(
      uni.getStorageSync('entrance_scene') ||
      uni.getStorageSync('tenant_id') ||
      customer.value.tenant_id
    ))

    const currentTableNo = computed(() =>
      uni.getStorageSync('table_no') ||
      customer.value.table_no ||
      ''
    )

    const storeSceneText = computed(() => {
      const table = currentTableNo.value
      if (!table) return ''
      return `${table}桌 · 堂食`
    })

    const storePhone = computed(() =>
      customer.value.shop_phone ||
      customer.value.tenant_phone ||
      customer.value.store_phone ||
      ''
    )

    const customerPhone = computed(() =>
      customer.value.phone ||
      uni.getStorageSync('customer_phone') ||
      ''
    )

    const customerAvatar = computed(() =>
      customer.value.avatar ||
      customer.value.avatar_url ||
      customer.value.headimgurl ||
      ''
    )

    const displayName = computed(() =>
      customer.value.nickname ||
      customer.value.nick_name ||
      customer.value.name ||
      '微信用户'
    )

    const lastVisitText = computed(() => formatShortDate(customer.value.last_consume_time || customer.value.last_visit_time))

    const recentOrderTime = computed(() => formatOrderTime(recentOrder.value?.createdAt || recentOrder.value?.created_at || recentOrder.value?.created_time))

    const recentOrderScene = computed(() => {
      const table = recentOrder.value?.table || recentOrder.value?.table_no || currentTableNo.value
      return table ? `${table}桌 · 堂食` : ''
    })

    const recentOrderSummary = computed(() => {
      const items = normalizeList(recentOrder.value?.items)
      if (!items.length) return '订单明细'
      const firstName = items[0].name || items[0].goods_name || items[0].dish_name || '菜品'
      const count = items.reduce((sum, item) => sum + Number(item.qty || item.quantity || item.count || 1), 0)
      return count > 1 ? `${firstName}等${count}件` : firstName
    })

    const loadProfile = async () => {
      const token = uni.getStorageSync('customer_token')
      isLoggedIn.value = Boolean(token)
      error.value = ''
      loadRecentOrder()

      if (!token) {
        customer.value = {}
        return
      }

      loading.value = true
      try {
        const profileRes = await getMemberProfile()
        if (profileRes.code === 200) {
          customer.value = profileRes.data || {}
        } else {
          error.value = profileRes.msg || '资料加载失败'
        }
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
      }
    }

    const loadRecentOrder = () => {
      recentOrder.value = null
      if (!uni.getStorageSync('customer_token')) return
      try {
        const info = uni.getStorageInfoSync()
        const orderKeys = (info.keys || []).filter((key) => key.indexOf('my_orders_') === 0)
        const orders = []
        orderKeys.forEach((key) => {
          const raw = uni.getStorageSync(key)
          if (!raw) return
          const list = JSON.parse(raw)
          if (Array.isArray(list)) orders.push(...list)
        })
        recentOrder.value = orders
          .filter(Boolean)
          .sort((a, b) => Number(b.createdTs || 0) - Number(a.createdTs || 0))[0] || null
      } catch (e) {
        recentOrder.value = null
      }
    }

    const statusLabel = (status) => ({
      pending: '等待接单',
      paid: '等待接单',
      accepted: '备餐中',
      preparing: '备餐中',
      done: '已完成',
      completed: '已完成',
      rejected: '已拒单',
      cancelled: '已取消',
      settled: '已结账'
    })[status] || '处理中'

    const go = (url) => uni.navigateTo({ url })

    const handleLoginAuth = async (event) => {
      if (authorizing.value) return
      const phoneCode = event?.detail?.code || event?.detail?.phoneCode || ''
      if (!phoneCode) return uni.showToast({ title: '未完成授权，请重试', icon: 'none' })
      if (!hasStoreContext.value) {
        uni.showModal({
          title: '请先扫描桌贴码',
          content: '需要识别门店后才能登录会员和查看订单。',
          cancelText: '稍后',
          confirmText: '去扫码',
          success: ({ confirm }) => {
            if (confirm) scanStoreCode()
          }
        })
        return
      }
      authorizing.value = true
      try {
        const code = await wxLogin()
        const res = await entryJoin({
          scene: uni.getStorageSync('entrance_scene') || '',
          tenant_id: uni.getStorageSync('tenant_id') || customer.value.tenant_id || '',
          table_no: currentTableNo.value || '',
          code,
          phone_code: phoneCode,
          agreement_accepted: true,
        })
        if (res?.code !== 200) {
          uni.showToast({ title: res?.msg || '登录失败，请重试', icon: 'none' })
          return
        }
        saveCustomerSession(res.data || {})
        isLoggedIn.value = true
        uni.showToast({ title: '已登录', icon: 'none' })
        await loadProfile()
      } catch (err) {
        uni.showToast({ title: err?.message || '登录失败，请重试', icon: 'none' })
      } finally {
        authorizing.value = false
      }
    }

    const routeByScanResult = (res = {}) => {
      const path = res.path || ''
      if (path) {
        const target = path.startsWith('/') ? path : `/${path}`
        uni.navigateTo({ url: target })
        return
      }

      const result = res.result || ''
      const sceneMatch = result.match(/[?&]scene=([^&]+)/)
      const scene = sceneMatch ? decodeURIComponent(sceneMatch[1]).trim() : result.trim()
      if (!scene) {
        uni.showToast({ title: '没有识别到桌贴码', icon: 'none' })
        return
      }
      uni.setStorageSync('entrance_scene', scene)
      uni.navigateTo({ url: `/pages/entry/index?scene=${encodeURIComponent(scene)}` })
    }

    const scanStoreCode = () => {
      uni.scanCode({
        onlyFromCamera: true,
        success: routeByScanResult,
        fail: () => {
          uni.showToast({ title: '请扫描桌贴点餐码', icon: 'none' })
        }
      })
    }

    const goLogin = () => {
      if (!hasStoreContext.value) {
        scanStoreCode()
        return
      }
      uni.showToast({ title: '请点上方微信快捷登录', icon: 'none' })
    }

    const goBindPhone = () => {
      go('/subpkg-member/pages/profile-edit')
    }

    const goOrders = () => {
      if (!isLoggedIn.value) {
        goLogin()
        return
      }
      if (recentOrder.value) {
        openRecentOrder()
        return
      }
      go('/subpkg-member/pages/consumptions')
    }

    const openRecentOrder = () => {
      const table = currentTableNo.value
      const shop = uni.getStorageSync('tenant_id') || customer.value.tenant_id || ''
      const query = [
        table ? `table=${encodeURIComponent(table)}` : '',
        shop ? `shop=${encodeURIComponent(shop)}` : '',
        'openOrders=1'
      ].filter(Boolean).join('&')
      uni.navigateTo({ url: `/subpkg-order/pages/menu${query ? `?${query}` : ''}` })
    }

    const showStoreInfo = () => {
      if (!hasStoreContext.value) {
        uni.showModal({
          title: '未识别门店',
          content: '请扫描桌贴点餐码进入门店。',
          cancelText: '稍后',
          confirmText: '去扫码',
          success: ({ confirm }) => {
            if (confirm) scanStoreCode()
          }
        })
        return
      }
      uni.showModal({
        title: '当前门店',
        content: storeSceneText.value ? `${currentStoreName.value}\n${storeSceneText.value}` : currentStoreName.value,
        showCancel: false,
        confirmText: '知道了'
      })
    }

    const callStore = () => {
      if (!storePhone.value) return
      uni.makePhoneCall({ phoneNumber: String(storePhone.value) })
    }

    const logout = () => {
      uni.showModal({
        title: '退出登录',
        content: '确定退出当前账号吗？',
        cancelText: '取消',
        confirmText: '确认退出',
        success: ({ confirm }) => {
          if (!confirm) return
          clearCustomerSession()
          isLoggedIn.value = false
          customer.value = {}
          recentOrder.value = null
          uni.showToast({ title: '已退出', icon: 'none' })
        }
      })
    }

    const openAgreement = (type) => {
      uni.navigateTo({ url: `/subpkg-member/pages/agreement?type=${type}` })
    }

    return {
      customer,
      loading,
      error,
      isLoggedIn,
      recentOrder,
      authorizing,
      currentStoreName,
      hasStoreContext,
      storeSceneText,
      storePhone,
      customerPhone,
      customerAvatar,
      displayName,
      lastVisitText,
      recentOrderTime,
      recentOrderScene,
      recentOrderSummary,
      loadProfile,
      goLogin,
      scanStoreCode,
      handleLoginAuth,
      goBindPhone,
      goOrders,
      openRecentOrder,
      showStoreInfo,
      callStore,
      logout,
      openAgreement,
      statusLabel,
      formatMoney,
      formatPhone
    }
  },
  onShow() {
    this.loadProfile()
  }
}
</script>

<style lang="scss">
.mine-page {
  min-height: 100vh;
  background: #F5F7F9;
}

.mine-content {
  padding: 32rpx 0 calc(140rpx + env(safe-area-inset-bottom));
}

.state-card {
  margin: 160rpx 32rpx 0;
  padding: 40rpx 32rpx;
  background: #fff;
  border-radius: 32rpx;
  text-align: center;
}

.spinner {
  width: 56rpx;
  height: 56rpx;
  margin: 0 auto 22rpx;
  border: 6rpx solid #d8f7e6;
  border-top-color: #07C160;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.state-title,
.state-desc,
.identity-name,
.identity-phone,
.identity-bind,
.store-label,
.store-name,
.store-scene,
.store-visit,
.section-title,
.order-summary,
.service-title,
.service-name,
.service-desc {
  display: block;
}

.state-title {
  color: #171A1D;
  font-size: 32rpx;
  font-weight: 700;
}

.state-desc {
  margin-top: 10rpx;
  color: #7D848E;
  font-size: 26rpx;
}

.primary-btn {
  margin-top: 28rpx;
  width: 100%;
  height: 96rpx;
  border-radius: 24rpx;
  background: #07C160;
  color: #fff;
  font-size: 30rpx;
  font-weight: 700;
}

.identity-card {
  min-height: 280rpx;
  margin: 0 32rpx;
  padding: 36rpx;
  background: #07C160;
  border-radius: 36rpx;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 24rpx;
}

.identity-avatar {
  width: 112rpx;
  height: 112rpx;
  border-radius: 56rpx;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.18);
}

.identity-avatar-default {
  display: flex;
  align-items: center;
  justify-content: center;
}

.identity-avatar-default text {
  color: #fff;
  font-size: 38rpx;
  font-weight: 800;
}

.identity-main {
  flex: 1;
  min-width: 0;
}

.identity-name {
  max-width: 100%;
  color: #fff;
  font-size: 40rpx;
  line-height: 56rpx;
  font-weight: 700;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.identity-phone {
  margin-top: 8rpx;
  color: rgba(255, 255, 255, 0.82);
  font-size: 28rpx;
  line-height: 40rpx;
}

.identity-bind {
  margin-top: 8rpx;
  color: rgba(255, 255, 255, 0.65);
  font-size: 24rpx;
  line-height: 34rpx;
}

.identity-sub-btn,
.identity-login-btn {
  flex-shrink: 0;
  height: 64rpx;
  padding: 0 24rpx;
  border-radius: 32rpx;
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  font-size: 24rpx;
  line-height: 64rpx;
}

.identity-login-btn {
  height: 72rpx;
  padding: 0 28rpx;
  background: #fff;
  color: #07C160;
  font-size: 26rpx;
  font-weight: 700;
  line-height: 72rpx;
}

.identity-login-btn::after { border: 0; }
.identity-login-btn[disabled] { opacity: .78; }

.store-card,
.recent-order-card,
.service-card {
  margin: 28rpx 32rpx 0;
  background: #fff;
  border-radius: 32rpx;
}

.store-card {
  padding: 32rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
}

.store-main {
  flex: 1;
  min-width: 0;
}

.store-label {
  color: #8A9099;
  font-size: 26rpx;
  line-height: 36rpx;
}

.store-name {
  margin-top: 16rpx;
  color: #171A1D;
  font-size: 34rpx;
  line-height: 48rpx;
  font-weight: 600;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.store-scene,
.store-visit {
  margin-top: 10rpx;
  color: #7D848E;
  font-size: 26rpx;
  line-height: 36rpx;
}

.card-arrow {
  color: #C3C8CF;
  font-size: 44rpx;
  line-height: 1;
  flex-shrink: 0;
}

.recent-order-card {
  padding: 30rpx 32rpx;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title,
.service-title {
  color: #171A1D;
  font-size: 34rpx;
  line-height: 48rpx;
  font-weight: 700;
}

.order-meta {
  margin-top: 18rpx;
  display: flex;
  align-items: center;
  gap: 20rpx;
  color: #7D848E;
  font-size: 26rpx;
  line-height: 36rpx;
}

.order-summary {
  margin-top: 16rpx;
  color: #171A1D;
  font-size: 30rpx;
  line-height: 42rpx;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.order-bottom {
  margin-top: 18rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.order-amount {
  color: #171A1D;
  font-size: 34rpx;
  font-weight: 800;
}

.order-status {
  color: #7D848E;
  font-size: 26rpx;
}

.service-card {
  overflow: hidden;
}

.service-title {
  padding: 30rpx 32rpx 8rpx;
}

.service-list {
  padding: 0 32rpx;
}

.service-row {
  min-height: 128rpx;
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.service-row:active,
.store-card:active,
.recent-order-card:active {
  background: #F6FBF8;
}

.service-icon {
  width: 72rpx;
  height: 72rpx;
  border-radius: 20rpx;
  background: #E9F9F0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.service-icon text {
  color: #07C160;
  font-size: 28rpx;
  font-weight: 800;
}

.service-copy {
  flex: 1;
  min-width: 0;
}

.service-name {
  color: #171A1D;
  font-size: 32rpx;
  line-height: 44rpx;
  font-weight: 600;
}

.service-desc {
  margin-top: 4rpx;
  color: #8A9099;
  font-size: 24rpx;
  line-height: 34rpx;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.service-divider {
  height: 1rpx;
  margin-left: 92rpx;
  background: #EEF1F4;
}

.logout-text-btn {
  margin: 34rpx auto 0;
  width: auto;
  height: 72rpx;
  padding: 0 34rpx;
  background: transparent;
  color: #8A9099;
  font-size: 28rpx;
  line-height: 72rpx;
}

.agreement-row {
  margin-top: 24rpx;
  padding-bottom: 8rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16rpx;
}

.agreement-link,
.agreement-sep {
  color: #A0A5AC;
  font-size: 24rpx;
  line-height: 34rpx;
}

button {
  margin: 0;
  border: 0;
}

button::after {
  border: 0;
}

@media screen and (max-width: 340px) {
  .identity-card {
    padding: 30rpx;
    gap: 18rpx;
  }

  .identity-avatar {
    width: 96rpx;
    height: 96rpx;
  }

  .identity-name {
    font-size: 36rpx;
  }

  .identity-login-btn {
    padding: 0 20rpx;
    font-size: 24rpx;
  }
}
</style>










