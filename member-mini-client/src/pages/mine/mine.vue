<template>
  <view class="mine-page">
    <order-bubble
      :visible="Boolean(activeTableOrder)"
      :tone="bubbleTone"
      :icon="bubbleIcon"
      :badge="bubbleBadge"
      :action-text="bubbleActionText"
      :count="activeTableOrders.length"
      :top-rpx="200"
      :bottom-clear-rpx="160"
      @click="openRecentOrder"
    />

    <view v-if="loading" class="state-card">
      <state-loading />
    </view>

    <view v-else-if="error" class="state-card">
      <state-error :title="error" desc="请稍后重试。" @retry="loadProfile" />
    </view>

    <view v-else class="mine-content">
      <view class="identity-card">
        <view class="identity-top">
          <image
            v-if="isLoggedIn && customerAvatar"
            class="identity-avatar"
            :src="customerAvatar"
            mode="aspectFill"
            @click="handleAvatarMultiTap"
          />
          <view v-else class="identity-avatar identity-avatar-default" @click="handleAvatarMultiTap">
            <text>{{ isLoggedIn ? '我' : '开' }}</text>
          </view>

          <view class="identity-main">
            <text class="identity-name">{{ isLoggedIn ? displayName : '未登录' }}</text>
            <text v-if="isLoggedIn && customerPhone" class="identity-phone">{{ formatPhone(customerPhone) }}</text>
            <text v-if="isLoggedIn" class="identity-bind">{{ customerPhone ? '已绑定手机号' : '未绑定手机号' }}</text>
            <view v-if="isLoggedIn" class="identity-stats tap-shrink" @click.stop="goGrowth">
              <text class="identity-level">{{ memberLevelLabel }}</text>
              <text class="identity-stats-sep">·</text>
              <text class="identity-points">积分 {{ memberPoints }}</text>
              <text class="identity-stats-arrow">›</text>
            </view>
          </view>

          <button v-if="isLoggedIn && !customerPhone" class="identity-sub-btn tap-shrink" @click="goBindPhone">去绑定</button>
          <button
            v-if="!isLoggedIn && hasStoreContext"
            class="identity-login-btn tap-shrink"
            open-type="getPhoneNumber"
            :disabled="authorizing"
            @getphonenumber="handleLoginAuth"
          >{{ authorizing ? '登录中…' : '微信快捷登录' }}</button>
          <button
            v-else-if="!isLoggedIn"
            class="identity-login-btn tap-shrink"
            :disabled="authorizing"
            @click="scanStoreCode"
          >扫码进入门店</button>
        </view>

        <view v-if="!isLoggedIn && hasStoreContext" class="identity-promo">
          <text class="identity-promo-icon">🎁</text>
          <text class="identity-promo-text">{{ newCustomerHookText }}</text>
        </view>
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
            <view class="service-icon"><text class="iconfont icon-order"></text></view>
            <view class="service-copy">
              <text class="service-name">我的订单</text>
              <text class="service-desc">{{ !isLoggedIn ? '登录后查看历史订单' : (recentOrder ? '查看历史订单和消费明细' : '暂无订单记录') }}</text>
            </view>
            <text class="card-arrow">›</text>
          </view>

          <view class="service-divider"></view>
          <view class="service-row" @click="goQueueTake">
            <view class="service-icon"><text class="iconfont icon-zuowei"></text></view>
            <view class="service-copy">
              <text class="service-name">排队取号</text>
              <text class="service-desc">{{ hasStoreContext ? '到店排队，叫号微信提醒' : '请先扫码进入门店' }}</text>
            </view>
            <text class="card-arrow">›</text>
          </view>

          <view v-if="isLoggedIn && inviteRewardEnabled" class="service-divider"></view>
          <view v-if="isLoggedIn && inviteRewardEnabled" class="service-row" @click="goInvite">
            <view class="service-icon"><text class="iconfont icon-ticket"></text></view>
            <view class="service-copy">
              <text class="service-name">邀请好友</text>
              <text class="service-desc">带朋友到店，双方都有优惠券</text>
            </view>
            <text class="card-arrow">›</text>
          </view>

          <view v-if="storePhone" class="service-divider"></view>
          <view v-if="storePhone" class="service-row" @click="callStore">
            <view class="service-icon"><text class="iconfont icon-phone"></text></view>
            <view class="service-copy">
              <text class="service-name">联系门店</text>
              <text class="service-desc">拨打门店电话</text>
            </view>
            <text class="card-arrow">›</text>
          </view>

        </view>
      </view>

      <button v-if="isLoggedIn" class="logout-text-btn tap-shrink" @click="logout">退出登录</button>

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
import { getShopInfo, getOrderStatus } from '@/api/order'
import { clearCustomerSession, saveCustomerSession } from '@/utils/auth'
import { scanStoreCode } from '@/utils/scan'
import { formatMoney, formatPhone } from '@/utils'
import { normalizeOrderStatus, orderStatusTone, orderStatusIcon, orderStatusBadge, orderStatusNextAction } from '@/utils/orderStatus'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'
import OrderBubble from '@/components/order-bubble/order-bubble.vue'

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
  components: { StateLoading, StateError, OrderBubble },
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

    const newCustomerCouponPreview = ref(null)   // { name, amount, min_amount, valid_days }
    // 跟点餐页(menu.vue)读同一个 /v1/shop/info 字段，保证登录按钮上写的数字
    // 和点餐页会员Tab、登录后弹出的新人券金额是同一个数据源、不会对不上。
    const newCustomerHookText = computed(() => {
      const p = newCustomerCouponPreview.value
      if (!p || !(p.amount > 0)) return '登录解锁会员专属优惠'
      const amount = formatMoney(p.amount)
      const min = Number(p.min_amount || 0)
      return min > 0 ? `新客立减¥${amount}，满${min.toFixed(0)}元可用` : `新客立减¥${amount}，授权手机号立得`
    })
    const inviteRewardEnabled = ref(false)   // 这家店有没有开"老带新双边奖励"，决定"邀请好友"入口显不显示
    const loadNewCustomerCouponPreview = async () => {
      if (!hasStoreContext.value) return
      const shop = uni.getStorageSync('tenant_id') || customer.value.tenant_id || ''
      if (!shop) return
      try {
        const res = await getShopInfo(shop)
        if (res?.code === 200) {
          newCustomerCouponPreview.value = res.data?.new_customer_coupon_preview || null
          inviteRewardEnabled.value = Boolean(res.data?.invite_reward_enabled)
        }
      } catch (e) {
        // 拿不到店铺的新客券预览/邀请开关配置，页面照常展示，只是少一块引导，不阻塞主流程。
      }
    }
    const goInvite = () => uni.navigateTo({ url: '/subpkg-member/pages/invite' })

    // 会话正常结束时 menu.vue 会主动清掉 table_no（见 menu.vue 里 tableSessionClosed
    // 的处理），这里再按时间兜底一层：如果店员在客户没重新打开点餐页的情况下远程结了
    // 账，table_no 可能没被及时清掉——超过后端会话过期时长（12小时，跟
    // dining_session_service.SESSION_EXPIRE_HOURS 对齐）就不再当成"当前在店"处理，
    // 避免顾客几天后打开小程序还看到"XX桌·堂食"这种和事实不符的提示。
    const TABLE_CONTEXT_STALE_MS = 12 * 60 * 60 * 1000
    const currentTableNo = computed(() => {
      const storedTable = uni.getStorageSync('table_no') || ''
      if (storedTable) {
        const storedAt = Number(uni.getStorageSync('table_no_at') || 0)
        if (storedAt && Date.now() - storedAt > TABLE_CONTEXT_STALE_MS) return ''
        return storedTable
      }
      return customer.value.table_no || ''
    })

    const storeSceneText = computed(() => {
      const table = currentTableNo.value
      if (!table) return ''
      return `${table}桌 · 堂食`
    })

    // 悬浮订单气泡：跟点餐页(menu.vue)共用同一份 my_orders_<shop>_<table> 本地缓存和
    // /v1/orders/my 轮询，这样顾客点完餐切到"我的"页面逛的时候，气泡还能继续跟着走，
    // 不会因为离开点餐页就看不到备餐进度。这里只做展示态的读取和刷新，真正的下单/
    // 取消等写操作还是在 menu.vue 里发生。
    const tableOrders = ref([])
    const tableOrdersStorageKey = () => {
      const shop = uni.getStorageSync('tenant_id') || customer.value.tenant_id || ''
      const table = currentTableNo.value
      return shop && table ? `my_orders_${shop}_${table}` : ''
    }
    const loadTableOrders = () => {
      const key = tableOrdersStorageKey()
      if (!key) { tableOrders.value = []; return }
      try {
        const raw = uni.getStorageSync(key)
        tableOrders.value = raw ? JSON.parse(raw) : []
      } catch (e) { tableOrders.value = [] }
    }
    const saveTableOrders = () => {
      const key = tableOrdersStorageKey()
      if (!key) return
      // 写不进本地缓存最多下次少看到一次悬浮气泡的历史订单，真实下单数据在服务端，不影响主流程。
      // eslint-disable-next-line no-empty
      try { uni.setStorageSync(key, JSON.stringify(tableOrders.value)) } catch (e) {}
    }
    const activeTableOrders = computed(() =>
      tableOrders.value.filter(o => !['cancelled', 'rejected', 'settled'].includes(normalizeOrderStatus(o.status)))
    )
    const activeTableOrder = computed(() => {
      if (!activeTableOrders.value.length) return null
      const rank = (o) => (['pending', 'preparing'].includes(normalizeOrderStatus(o.status)) ? 0 : 1)
      return [...activeTableOrders.value].sort((a, b) => rank(a) - rank(b))[0]
    })
    const bubbleTone = computed(() => orderStatusTone(activeTableOrder.value?.status))
    const bubbleIcon = computed(() => orderStatusIcon(bubbleTone.value))
    const bubbleBadge = computed(() => orderStatusBadge(bubbleTone.value))
    const bubbleActionText = computed(() => orderStatusNextAction(bubbleTone.value))

    let orderBubblePollTimer = null
    const pollActiveTableOrder = () => {
      const order = activeTableOrder.value
      if (!order) return
      const participantToken = uni.getStorageSync('dining_participant_token') || ''
      getOrderStatus(order.id, participantToken).then((body) => {
        if (body.code === 200) {
          const newStatus = body.data?.status || order.status
          const rec = tableOrders.value.find(o => o.id === order.id)
          if (rec && rec.status !== newStatus) {
            rec.status = newStatus
            saveTableOrders()
          }
        }
      }).catch(() => {})
    }
    const startOrderBubblePoll = () => {
      stopOrderBubblePoll()
      loadTableOrders()
      if (!activeTableOrder.value) return
      pollActiveTableOrder()
      orderBubblePollTimer = setInterval(pollActiveTableOrder, 15000)
    }
    const stopOrderBubblePoll = () => {
      if (orderBubblePollTimer) { clearInterval(orderBubblePollTimer); orderBubblePollTimer = null }
    }

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

    const memberLevelLabel = computed(() => customer.value.level || '普通会员')
    const memberPoints = computed(() => customer.value.points ?? 0)
    const goGrowth = () => go('/subpkg-member/pages/growth')

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
      // 新客券预览（未登录用）和邀请奖励开关（登录后要不要显示"邀请好友"入口）
      // 共用同一个 /v1/shop/info 请求，两种登录态都要跑，所以放在 token 判断之前。
      loadNewCustomerCouponPreview()

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

    const returnToOrdering = () => {
      if (!hasStoreContext.value) return
      const pages = getCurrentPages()
      if (pages.length > 1) {
        uni.navigateBack()
        return
      }
      const table = currentTableNo.value
      const shop = uni.getStorageSync('tenant_id') || customer.value.tenant_id || ''
      const query = [
        table ? `table=${encodeURIComponent(table)}` : '',
        shop ? `shop=${encodeURIComponent(shop)}` : ''
      ].filter(Boolean).join('&')
      uni.redirectTo({ url: `/subpkg-order/pages/menu${query ? `?${query}` : ''}` })
    }

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
          invite_code: uni.getStorageSync('invite_code') || '',
        }, { authRedirect: false })
        if (res?.code !== 200) {
          uni.showToast({ title: res?.msg || '登录失败，请重试', icon: 'none' })
          return
        }
        // 邀请码是一次性的，绑定动作后端只在"确实是新客户"时才生效——
        // 不管这次有没有真的绑上，用过就清掉，避免以后在别的店误用。
        uni.removeStorageSync('invite_code')
        saveCustomerSession(res.data || {})
        isLoggedIn.value = true
        uni.showToast({ title: '已登录', icon: 'none' })
        await loadProfile()
        returnToOrdering()
      } catch (err) {
        uni.showToast({ title: err?.message || '登录失败，请重试', icon: 'none' })
      } finally {
        authorizing.value = false
      }
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

    const goQueueTake = () => {
      const shop = String(uni.getStorageSync('tenant_id') || customer.value.tenant_id || '').trim()
      if (!shop) {
        uni.showModal({
          title: '未识别门店',
          content: '请先扫描门店码或桌贴码进入门店，再排队取号。',
          cancelText: '稍后',
          confirmText: '去扫码',
          success: ({ confirm }) => {
            if (confirm) scanStoreCode()
          },
        })
        return
      }
      uni.navigateTo({
        url: `/subpkg-common/pages/queue-take?shop=${encodeURIComponent(shop)}`,
        fail: (err) => {
          uni.showToast({ title: '打开失败：' + (err?.errMsg || '请重试'), icon: 'none' })
        },
      })
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

    // 连点头像 5 次进性能自测页——这是给开发/测试用的入口，不该在正式界面上留一个
    // "性能统计"入口给顾客看，藏在一个顾客不会误触的手势后面，2 秒内点不满 5 次就重新计数。
    // 每次点击都给个轻提示：这个手势本身完全无视觉反馈，点中没点中、还差几次全靠猜，
    // 排查起来跟"到底有没有生效"分不清——干脆每次点都报进度，最后跳转失败也报出来
    // （小程序页面栈超过10层 navigateTo 会静默失败），不再有"点了但不知道有没有用"的状态。
    let avatarTapCount = 0
    let avatarTapTimer = null
    const handleAvatarMultiTap = () => {
      avatarTapCount += 1
      clearTimeout(avatarTapTimer)
      avatarTapTimer = setTimeout(() => { avatarTapCount = 0 }, 2000)
      if (avatarTapCount >= 5) {
        avatarTapCount = 0
        clearTimeout(avatarTapTimer)
        uni.navigateTo({
          url: '/subpkg-common/pages/perf-debug',
          fail: (err) => {
            uni.showToast({ title: '跳转失败：' + (err?.errMsg || '未知原因'), icon: 'none', duration: 2500 })
          },
        })
        return
      }
      uni.showToast({ title: `再点 ${5 - avatarTapCount} 次进性能自测`, icon: 'none', duration: 700 })
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
      newCustomerCouponPreview,
      newCustomerHookText,
      loadNewCustomerCouponPreview,
      inviteRewardEnabled,
      goInvite,
      storeSceneText,
      storePhone,
      customerPhone,
      handleAvatarMultiTap,
      customerAvatar,
      displayName,
      lastVisitText,
      memberLevelLabel,
      memberPoints,
      goGrowth,
      recentOrderTime,
      recentOrderScene,
      recentOrderSummary,
      loadProfile,
      goLogin,
      scanStoreCode,
      handleLoginAuth,
      goBindPhone,
      goOrders,
      goQueueTake,
      openRecentOrder,
      showStoreInfo,
      callStore,
      logout,
      openAgreement,
      statusLabel,
      formatMoney,
      formatPhone,
      activeTableOrder,
      activeTableOrders,
      bubbleTone,
      bubbleIcon,
      bubbleBadge,
      bubbleActionText,
      startOrderBubblePoll,
      stopOrderBubblePoll
    }
  },
  onShow() {
    this.loadProfile()
    this.startOrderBubblePoll()
  },
  onHide() {
    this.stopOrderBubblePoll()
  },
  onUnload() {
    this.stopOrderBubblePoll()
  }
}
</script>

<style lang="scss">
.mine-page {
  min-height: 100vh;
  background: var(--bg-page);
}

.mine-content {
  padding: 32rpx 0 calc(140rpx + env(safe-area-inset-bottom));
}

.state-card {
  margin: 160rpx 32rpx 0;
  padding: 40rpx 32rpx;
  background: var(--bg-card);
  border-radius: var(--radius-hero);
  box-shadow: var(--card-shadow);
  text-align: center;
}

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

.identity-card {
  margin: 0 32rpx;
  padding: 36rpx;
  background: var(--brand-gradient);
  border-radius: var(--radius-hero);
  color: var(--text-inverse);
}

.identity-top {
  min-height: 208rpx;
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
  color: var(--text-inverse);
  font-size: 38rpx;
  font-weight: 800;
}

.identity-main {
  flex: 1;
  min-width: 0;
}

.identity-name {
  max-width: 100%;
  color: var(--text-inverse);
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

.identity-promo {
  margin-top: 24rpx;
  padding: 18rpx 24rpx;
  background: rgba(255, 255, 255, 0.16);
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.identity-promo-icon {
  font-size: 32rpx;
  line-height: 1;
  flex-shrink: 0;
}

.identity-promo-text {
  flex: 1;
  color: #fff7e0;
  font-size: 26rpx;
  font-weight: 700;
  line-height: 36rpx;
}

.identity-stats {
  display: inline-flex;
  align-items: center;
  margin-top: 14rpx;
  padding: 8rpx 18rpx;
  background: rgba(255, 255, 255, 0.16);
  border-radius: 999rpx;
}

.identity-level {
  color: #fff7e0;
  font-size: 24rpx;
  font-weight: 700;
  line-height: 34rpx;
}

.identity-stats-sep {
  margin: 0 10rpx;
  color: rgba(255, 255, 255, 0.5);
  font-size: 24rpx;
}

.identity-points {
  color: rgba(255, 255, 255, 0.9);
  font-size: 24rpx;
  line-height: 34rpx;
}

.identity-stats-arrow {
  margin-left: 8rpx;
  color: rgba(255, 255, 255, 0.6);
  font-size: 28rpx;
  line-height: 1;
}

.identity-sub-btn,
.identity-login-btn {
  flex-shrink: 0;
  height: 64rpx;
  padding: 0 24rpx;
  border-radius: 32rpx;
  background: rgba(255, 255, 255, 0.18);
  color: var(--text-inverse);
  font-size: 24rpx;
  line-height: 64rpx;
}

.identity-login-btn {
  height: 72rpx;
  padding: 0 28rpx;
  background: var(--bg-card);
  color: var(--brand);
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
  background: var(--bg-card);
  border-radius: var(--radius-hero);
  box-shadow: var(--card-shadow);
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
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 36rpx;
}

.store-name {
  margin-top: 16rpx;
  color: var(--text-1);
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
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 36rpx;
}

.card-arrow {
  color: var(--text-3);
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
  color: var(--text-1);
  font-size: 34rpx;
  line-height: 48rpx;
  font-weight: 700;
}

.order-meta {
  margin-top: 18rpx;
  display: flex;
  align-items: center;
  gap: 20rpx;
  color: var(--text-3);
  font-size: 26rpx;
  line-height: 36rpx;
}

.order-summary {
  margin-top: 16rpx;
  color: var(--text-1);
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
  color: var(--text-1);
  font-size: 34rpx;
  font-weight: 800;
}

.order-status {
  color: var(--text-3);
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
  background: var(--brand-light);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.service-icon text {
  color: var(--brand);
  font-size: 36rpx;
  line-height: 40rpx;
  font-weight: 400;
}

.service-copy {
  flex: 1;
  min-width: 0;
}

.service-name {
  color: var(--text-1);
  font-size: 32rpx;
  line-height: 44rpx;
  font-weight: 600;
}

.service-desc {
  margin-top: 4rpx;
  color: var(--text-3);
  font-size: 24rpx;
  line-height: 34rpx;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.service-divider {
  height: 1rpx;
  margin-left: 92rpx;
  background: var(--border);
}

.logout-text-btn {
  margin: 34rpx auto 0;
  width: auto;
  height: 72rpx;
  padding: 0 34rpx;
  background: transparent;
  color: var(--text-3);
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
  color: var(--text-3);
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










