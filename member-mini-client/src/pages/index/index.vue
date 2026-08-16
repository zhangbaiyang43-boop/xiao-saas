<template>
  <view class="entry-router-page">
    <view class="entry-card">
      <view class="entry-mark">开</view>
      <text class="entry-title">正在进入开心点单</text>
      <text class="entry-desc">{{ desc }}</text>
      <button class="entry-primary" @click="goOrder">{{ hasContext ? '继续点餐' : '扫码点餐' }}</button>
      <button class="entry-secondary" @click="goMine">我的</button>
    </view>
  </view>
</template>

<script>
import { ref } from 'vue'
import '@/utils/route'
import { scanStoreCode } from '@/utils/scan'
import { markEventOnce, markStart, recordDurationFromStart } from '@/utils/perf'

const TABLE_TTL = 4 * 60 * 60 * 1000

const getValidTableNo = () => {
  const table = uni.getStorageSync('table_no') || ''
  if (!table) return ''
  const savedAt = Number(uni.getStorageSync('table_no_at') || 0)
  if (!savedAt) return table
  return Date.now() - savedAt < TABLE_TTL ? table : ''
}

const buildMenuUrl = () => {
  const shop = uni.getStorageSync('tenant_id') || ''
  if (!shop) return ''

  const table = getValidTableNo()
  const query = [`shop=${encodeURIComponent(shop)}`]
  if (table) query.push(`table=${encodeURIComponent(table)}`)
  return `/subpkg-order/pages/menu?${query.join('&')}`
}
const buildEntryUrlFromOptions = (options = {}) => {
  const keys = ['scene', 'q', 'tenant_id', 'merchant_id', 'shop', 'store_id', 'table', 'table_no', 'desk', 'desk_no', 'table_id', 'desk_id', 'entry_type', 'channel', 'order_mode']
  const query = []
  keys.forEach((key) => {
    const value = options[key]
    if (value !== undefined && value !== null && String(value).trim()) {
      query.push(`${key}=${encodeURIComponent(String(value).trim())}`)
    }
  })
  return query.length ? `/pages/entry/index?${query.join('&')}` : ''
}

export default {
  setup() {
    const desc = ref('正在根据当前门店打开页面')
    const redirecting = ref(false)
    const hasContext = ref(false)

    const redirect = () => {
      if (redirecting.value) return
      const url = buildMenuUrl()
      hasContext.value = Boolean(url)
      if (!url) {
        desc.value = '请扫描桌上的点餐码进入门店'
        return
      }
      redirecting.value = true
      markStart('entry_to_menu')
      setTimeout(() => {
        uni.reLaunch({
          url,
          complete: () => {
            redirecting.value = false
          }
        })
      }, 80)
    }

    const goOrder = () => {
      const menuUrl = buildMenuUrl()
      hasContext.value = Boolean(menuUrl)
      if (!menuUrl) {
        scanStoreCode()
        return
      }
      markStart('entry_to_menu')
      uni.reLaunch({ url: menuUrl })
    }

    const goMine = () => {
      uni.reLaunch({ url: '/pages/mine/mine' })
    }

    return {
      desc,
      hasContext,
      redirect,
      goOrder,
      goMine
    }
  },
  onLoad(options = {}) {
    const entryUrl = buildEntryUrlFromOptions(options)
    if (entryUrl) {
      uni.reLaunch({ url: entryUrl })
      return
    }
    if (markEventOnce('entry_onload', 'entry_onload')) {
      recordDurationFromStart('launch_to_entry', 'launch_to_entry')
    }
    this.redirect()
  },
  onShow() {
    this.redirect()
  }
}
</script>

<style lang="scss">
.entry-router-page {
  min-height: 100vh;
  padding: 160rpx 32rpx 48rpx;
  box-sizing: border-box;
  background: #F5F7F9;
}

.entry-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 56rpx 32rpx 40rpx;
  background: #FFFFFF;
  border-radius: 32rpx;
  box-sizing: border-box;
}

.entry-mark {
  width: 96rpx;
  height: 96rpx;
  border-radius: 48rpx;
  background: #E8F9F0;
  color: #07C160;
  font-size: 44rpx;
  font-weight: 800;
  line-height: 96rpx;
  text-align: center;
}

.entry-title {
  margin-top: 28rpx;
  color: #171A1D;
  font-size: 36rpx;
  font-weight: 800;
  line-height: 48rpx;
}

.entry-desc {
  margin-top: 12rpx;
  color: #8A9099;
  font-size: 28rpx;
  line-height: 40rpx;
  text-align: center;
}

.entry-primary,
.entry-secondary {
  width: 100%;
  height: 96rpx;
  line-height: 96rpx;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 48rpx;
  font-size: 32rpx;
  font-weight: 700;
  text-align: center;
  box-sizing: border-box;
}

.entry-primary::after,
.entry-secondary::after {
  border: 0;
}

.entry-primary {
  margin-top: 48rpx;
  background: #07C160;
  color: #FFFFFF;
}

.entry-secondary {
  margin-top: 20rpx;
  background: #F1F3F5;
  color: #3F4650;
}
</style>
