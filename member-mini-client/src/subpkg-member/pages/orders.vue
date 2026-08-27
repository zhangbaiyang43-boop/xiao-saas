<template>
  <view class="page">
    <view class="page-header">
      <text class="ph-title">我的订单</text>
      <text class="ph-desc">这里显示本店已完成的历史订单。</text>
    </view>

    <view v-if="loading && !orders.length" class="state-wrap">
      <state-loading text="正在加载订单" />
    </view>

    <view v-else-if="error" class="state-wrap">
      <state-error :title="error" retry-text="刷新重试" @retry="reload" />
    </view>

    <view v-else-if="!orders.length" class="state-wrap">
      <state-empty
        icon="🧾"
        title="暂无订单"
        desc="在本店完成点餐后，历史订单会显示在这里。"
        action-text="去点餐"
        @action="goOrder"
      />
    </view>

    <view v-else class="record-list">
      <view
        v-for="item in orders"
        :key="item.order_id"
        class="record-card tap-shrink"
        @click="explainNoDetail"
      >
        <view class="rc-left">
          <view class="rc-title-row">
            <text class="rc-title">{{ formatOrderStatusText(item.status, item.status_text) }}</text>
            <text v-if="item.refund_required" class="rc-refund">需商家退款</text>
          </view>
          <text class="rc-time">{{ formatDateTime(item.created_at) }}</text>
          <text v-if="item.pickup_no" class="rc-meta">桌牌 {{ item.pickup_no }} 号 · {{ item.dish_count || 0 }}份</text>
          <text v-else class="rc-meta">{{ item.dish_count || 0 }}份</text>
        </view>
        <text class="rc-amount">¥{{ formatMoney(item.total) }}</text>
      </view>
      <view v-if="hasMore" class="more-wrap">
        <text class="more-text" @click="loadMore">{{ loadingMore ? '加载中…' : '加载更多' }}</text>
      </view>
    </view>
  </view>
</template>

<script>
import { computed, ref } from 'vue'
import { getMyOrders } from '@/api/order'
import { formatDateTime, formatMoney } from '@/utils'
import { formatOrderStatusText } from '@/utils/orderStatus'
import StateLoading from '@/components/state-loading/state-loading.vue'
import StateError from '@/components/state-error/state-error.vue'
import StateEmpty from '@/components/state-empty/state-empty.vue'

const PAGE_SIZE = 20

export default {
  components: { StateLoading, StateError, StateEmpty },
  setup() {
    const loading = ref(false)
    const loadingMore = ref(false)
    const error = ref('')
    const orders = ref([])
    const total = ref(0)
    const hasMore = computed(() => orders.value.length < total.value)

    const pageItems = (data) => {
      if (Array.isArray(data)) return data
      if (Array.isArray(data?.items)) return data.items
      if (Array.isArray(data?.list)) return data.list
      return []
    }

    const load = async ({ append = false } = {}) => {
      if (!uni.getStorageSync('customer_token')) {
        uni.reLaunch({ url: '/pages/mine/mine' })
        return
      }
      if (append) loadingMore.value = true
      else {
        loading.value = true
        error.value = ''
      }
      try {
        const skip = append ? orders.value.length : 0
        const res = await getMyOrders(skip, PAGE_SIZE)
        if (res.code === 200) {
          const rows = pageItems(res.data)
          total.value = Number(res.data?.total || rows.length)
          orders.value = append ? orders.value.concat(rows) : rows
        } else {
          error.value = res.msg || '订单加载失败'
        }
      } catch (err) {
        error.value = err.message || '网络不稳定，请稍后再试'
      } finally {
        loading.value = false
        loadingMore.value = false
      }
    }

    const reload = () => load({ append: false })
    const loadMore = () => {
      if (loading.value || loadingMore.value || !hasMore.value) return
      load({ append: true })
    }
    const explainNoDetail = () => {
      uni.showToast({
        title: '菜品明细请在本桌订单里查看',
        icon: 'none',
        duration: 2000,
      })
    }
    const goOrder = () => {
      // 这只是"回到点餐页时顺便帮你切到订单 tab"的一个提示，存不进去
      // （存储满/被清）也不影响跳转本身，所以吞掉不报错。
      try { uni.setStorageSync('menu_focus_tab', 'order') } catch { /* 存不进去就正常跳转，不影响主流程 */ }
      const pages = getCurrentPages()
      const idx = pages.findIndex(p => (p.route || '').indexOf('subpkg-order/pages/menu') !== -1)
      if (idx >= 0) {
        uni.navigateBack({ delta: pages.length - 1 - idx })
        return
      }
      uni.showToast({ title: '请先扫桌台二维码点餐', icon: 'none' })
    }

    return {
      loading,
      loadingMore,
      error,
      orders,
      hasMore,
      reload,
      loadMore,
      explainNoDetail,
      goOrder,
      formatDateTime,
      formatMoney,
      formatOrderStatusText,
    }
  },
  onShow() {
    this.reload()
  }
}
</script>

<style lang="scss">
.page {
  min-height: 100vh;
  background: #F7F8FA;
}

.page-header {
  padding: 48rpx 32rpx 40rpx;
  background: var(--brand);
}

.ph-title {
  display: block;
  color: #fff;
  font-size: 44rpx;
  font-weight: bold;
  line-height: 1.3;
}

.ph-desc {
  display: block;
  margin-top: 12rpx;
  color: rgba(255, 255, 255, 0.85);
  font-size: 26rpx;
}

.state-wrap {
  margin: 48rpx 24rpx 0;
  padding: 64rpx 32rpx;
  background: #fff;
  border-radius: 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

.record-list {
  padding: 24rpx 24rpx 32rpx;
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.record-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx;
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.05);
}

.rc-left {
  flex: 1;
  min-width: 0;
  margin-right: 24rpx;
}

.rc-title-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.rc-title {
  color: #111;
  font-size: 32rpx;
  font-weight: 600;
}

.rc-refund {
  color: #dc2626;
  font-size: 22rpx;
}

.rc-time,
.rc-meta {
  display: block;
  margin-top: 8rpx;
  color: #999;
  font-size: 24rpx;
}

.rc-amount {
  color: #111;
  font-size: 32rpx;
  font-weight: 700;
}

.more-wrap {
  padding: 8rpx 0 24rpx;
  text-align: center;
}

.more-text {
  color: var(--brand);
  font-size: 26rpx;
}
</style>
