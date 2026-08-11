<template>
  <view class="page">
    <view v-if="bootError" class="card state-card">
      <text class="state-title">无法取号</text>
      <text class="state-desc">{{ bootError }}</text>
    </view>

    <template v-else-if="ticket">
      <view class="card result-card">
        <text class="shop-name">{{ shopName || '门店排队' }}</text>
        <text class="result-label">您的排队号</text>
        <text class="queue-no">{{ ticket.queue_no }}</text>
        <view class="meta-row">
          <text>{{ ticket.queue_type_name || '' }}</text>
          <text>{{ ticket.party_size }}人</text>
        </view>
        <view class="wait-box">
          <text class="wait-main">{{ ticket.waiting_text || ('前方等待' + (ticket.ahead_count ?? 0) + '桌') }}</text>
          <text class="wait-sub">{{ ticket.estimated_wait_text || '' }}</text>
        </view>
        <text class="tip">叫到号时会通过微信服务通知提醒您，请留意手机。</text>
        <button class="btn-primary" :loading="refreshing" @click="refreshStatus">刷新进度</button>
        <button class="btn-plain" @click="resetTake">再取一号</button>
      </view>
    </template>

    <template v-else>
      <view class="card">
        <text class="shop-name">{{ shopName || '排队取号' }}</text>
        <text class="section-label">用餐人数</text>
        <view class="size-row">
          <view
            v-for="opt in partyOptions"
            :key="opt.size"
            class="size-chip"
            :class="{ active: partySize === opt.size }"
            @click="partySize = opt.size"
          >
            <text class="size-num">{{ opt.label }}</text>
            <text class="size-type">{{ opt.typeName }}</text>
          </view>
        </view>
        <button class="btn-primary" :loading="submitting" :disabled="!shopId || submitting" @click="takeNumber">
          取号
        </button>
        <text class="hint">取号前可勾选「排队提醒」，叫到号时微信通知您。</text>
      </view>
    </template>
  </view>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import { getShopInfo } from '@/api/order'
import { loginOrCreateMember } from '@/api/auth'
import { createCustomerQueueTicket, getMyActiveQueueTicket, getQueueTicketStatusByToken } from '@/api/queue'
import { hasCustomerToken, saveCustomerSession } from '@/utils/auth'

const partyOptions = [
  { size: 2, label: '1-2人', typeName: '小桌' },
  { size: 4, label: '3-4人', typeName: '中桌' },
  { size: 6, label: '5人及以上', typeName: '大桌' },
]

export default {
  setup() {
    const shopId = ref('')
    const shopName = ref('')
    const queueReminderTemplateId = ref('')
    const partySize = ref(2)
    const submitting = ref(false)
    const refreshing = ref(false)
    const bootError = ref('')
    const ticket = ref(null)
    let pollTimer = null

    const wxLogin = () => new Promise((resolve, reject) => {
      uni.login({
        provider: 'weixin',
        success: (res) => (res.code ? resolve(res.code) : reject(new Error('微信登录失败'))),
        fail: () => reject(new Error('微信登录失败')),
      })
    })

    const ensureCustomerLogin = async () => {
      if (hasCustomerToken() && String(uni.getStorageSync('tenant_id') || '') === shopId.value) {
        return true
      }
      const code = await wxLogin()
      const res = await loginOrCreateMember({ tenant_id: shopId.value, code })
      if (res?.code !== 200 || !res?.data?.token) {
        throw new Error(res?.msg || '登录失败，请重试')
      }
      saveCustomerSession(res.data)
      return true
    }

    const requestQueueSubscribe = async () => {
      const id = queueReminderTemplateId.value
      if (!id) return
      await new Promise((resolve) => {
        try {
          uni.requestSubscribeMessage({
            tmplIds: [id],
            complete: resolve,
            fail: resolve,
          })
        } catch (e) {
          resolve()
        }
      })
    }

    const stopPoll = () => {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }

    const startPoll = () => {
      stopPoll()
      if (!ticket.value?.query_token) return
      pollTimer = setInterval(() => {
        refreshStatus({ silent: true }).catch(() => {})
      }, 15000)
    }

    const refreshStatus = async ({ silent = false } = {}) => {
      const token = ticket.value?.query_token
      if (!token) return
      if (!silent) refreshing.value = true
      try {
        const res = await getQueueTicketStatusByToken(token)
        const d = res?.data || {}
        ticket.value = {
          ...ticket.value,
          queue_no: d.queue_no || d.queue_number || ticket.value.queue_no,
          queue_type_name: d.queue_type_name || ticket.value.queue_type_name,
          party_size: d.party_size ?? ticket.value.party_size,
          ahead_count: d.ahead_count,
          waiting_text: d.waiting_text,
          estimated_wait_text: d.estimated_wait_text,
          status: d.status,
          status_text: d.status_text,
        }
        if (['seated', 'skipped', 'cancelled'].includes(d.status)) stopPoll()
      } catch (e) {
        if (!silent) uni.showToast({ title: e.message || '刷新失败', icon: 'none' })
      } finally {
        if (!silent) refreshing.value = false
      }
    }

    const takeNumber = async () => {
      if (submitting.value || !shopId.value) return
      submitting.value = true
      try {
        await ensureCustomerLogin()
        // 必须在用户点击取号的手势链里申请订阅
        await requestQueueSubscribe()
        const res = await createCustomerQueueTicket({
          shop: shopId.value,
          party_size: partySize.value,
        }, { authRedirect: false })
        if (res?.code !== 200 || !res?.data?.queue_no) {
          throw new Error(res?.msg || '取号失败，请重试')
        }
        ticket.value = res.data
        startPoll()
        uni.showToast({ title: '取号成功', icon: 'success' })
      } catch (e) {
        uni.showToast({ title: String(e.message || '取号失败').slice(0, 30), icon: 'none' })
      } finally {
        submitting.value = false
      }
    }

    const resetTake = () => {
      stopPoll()
      ticket.value = null
    }

    const loadShop = async () => {
      try {
        const res = await getShopInfo(shopId.value)
        const d = res?.data || {}
        shopName.value = d.name || d.shop_name || uni.getStorageSync('tenant_name') || ''
        queueReminderTemplateId.value = d.queue_reminder_template_id || ''
        if (shopName.value) {
          uni.setNavigationBarTitle({ title: shopName.value + ' 排队' })
        }
      } catch (e) {
        bootError.value = e.message || '门店信息加载失败'
      }
    }

    // 进页面时如果这个顾客在本店已经有一张还没被叫到/坐下的活跃号，直接把它显示出来，
    // 不要求再点一次"取号"——不然顾客退出小程序再进来看到的永远是"取号"按钮，一按
    // 就以为是重新排队（虽然后端 create_ticket 现在幂等，不会真的插队，但界面上应该
    // 直接就是"你已经在排队了"，不用靠再点一次按钮去发现这件事）。只在顾客已经登录过
    // （之前取过号必然登录过）时才查，不对还没登录的新访客强制弹微信授权。
    const restoreExistingTicket = async () => {
      if (!hasCustomerToken() || String(uni.getStorageSync('tenant_id') || '') !== shopId.value) return
      try {
        const res = await getMyActiveQueueTicket(shopId.value, { authRedirect: false })
        if (res?.code === 200 && res?.data?.queue_no) {
          ticket.value = res.data
          startPoll()
        }
      } catch (e) {
        // 查询失败就当没有活跃号处理，正常走"取号"入口，不打扰用户
      }
    }

    onMounted(() => {
      const pages = getCurrentPages()
      const page = pages[pages.length - 1]
      const q = page?.options || {}
      shopId.value = String(q.shop || q.tenant_id || uni.getStorageSync('tenant_id') || '').trim()
      if (!shopId.value) {
        bootError.value = '缺少门店参数，请从门店码进入'
        return
      }
      loadShop()
      restoreExistingTicket()
    })

    onUnmounted(stopPoll)

    return {
      shopId,
      shopName,
      partyOptions,
      partySize,
      submitting,
      refreshing,
      bootError,
      ticket,
      takeNumber,
      refreshStatus,
      resetTake,
    }
  },
}
</script>

<style lang="scss" scoped>
.page {
  min-height: 100vh;
  padding: var(--page-pad);
  background: var(--bg-page);
  box-sizing: border-box;
}
.card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 40rpx 32rpx;
  box-shadow: var(--card-shadow);
}
.shop-name {
  display: block;
  font-size: 34rpx;
  font-weight: 800;
  color: var(--text-1);
  margin-bottom: 32rpx;
}
.section-label {
  display: block;
  font-size: 26rpx;
  color: var(--text-3);
  margin-bottom: 16rpx;
}
.size-row {
  display: flex;
  gap: 16rpx;
  margin-bottom: 40rpx;
}
.size-chip {
  flex: 1;
  border: 2rpx solid var(--border);
  border-radius: 20rpx;
  padding: 24rpx 12rpx;
  text-align: center;
  background: var(--bg-muted);
}
.size-chip.active {
  border-color: var(--brand);
  background: var(--brand-light);
}
.size-num {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: var(--text-1);
}
.size-type {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  color: var(--text-3);
}
.btn-primary {
  height: var(--btn-primary-height);
  line-height: var(--btn-primary-height);
  border-radius: var(--btn-primary-radius);
  background: var(--brand);
  color: var(--text-inverse);
  font-size: var(--btn-primary-font-size);
  font-weight: var(--btn-primary-font-weight);
  border: none;
}
.btn-primary[disabled] {
  opacity: 0.45;
}
.btn-plain {
  margin-top: 20rpx;
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 44rpx;
  background: var(--bg-muted);
  color: var(--text-2);
  font-size: 28rpx;
  border: none;
}
.hint {
  display: block;
  margin-top: 20rpx;
  font-size: 22rpx;
  color: var(--text-3);
  line-height: 1.5;
}
.result-card {
  text-align: center;
}
.result-label {
  display: block;
  font-size: 26rpx;
  color: var(--text-3);
}
.queue-no {
  display: block;
  margin: 12rpx 0 20rpx;
  font-size: 96rpx;
  font-weight: 900;
  color: var(--brand-dark);
  line-height: 1.1;
}
.meta-row {
  display: flex;
  justify-content: center;
  gap: 24rpx;
  font-size: 26rpx;
  color: var(--text-2);
  margin-bottom: 28rpx;
}
.wait-box {
  background: var(--brand-light);
  border-radius: 20rpx;
  padding: 28rpx;
  margin-bottom: 24rpx;
}
.wait-main {
  display: block;
  font-size: 30rpx;
  font-weight: 700;
  color: var(--text-1);
}
.wait-sub {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: var(--text-3);
}
.tip {
  display: block;
  margin-bottom: 32rpx;
  font-size: 24rpx;
  color: var(--text-3);
  line-height: 1.5;
}
.state-card {
  text-align: center;
  padding: 80rpx 40rpx;
}
.state-title {
  display: block;
  font-size: 34rpx;
  font-weight: 800;
  color: var(--text-1);
}
.state-desc {
  display: block;
  margin-top: 16rpx;
  font-size: 26rpx;
  color: var(--text-3);
}
</style>
