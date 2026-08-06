<template>
  <view class="perf-page">
    <view class="perf-hint">本地采样，最近 60 次，仅这台设备可见；用来对比优化前后有没有真的变快。</view>
    <view v-for="row in stats" :key="row.metric" class="perf-card">
      <view class="perf-card-title">{{ labelOf(row.metric) }}</view>
      <view v-if="row.count === 0" class="perf-empty">还没有样本，去正常走一遍这个操作再回来看</view>
      <view v-else class="perf-grid">
        <view class="perf-cell"><text class="perf-cell-label">次数</text><text class="perf-cell-value">{{ row.count }}</text></view>
        <view class="perf-cell"><text class="perf-cell-label">P50</text><text class="perf-cell-value">{{ row.p50 }}ms</text></view>
        <view class="perf-cell perf-cell--warn"><text class="perf-cell-label">P95</text><text class="perf-cell-value">{{ row.p95 }}ms</text></view>
        <view class="perf-cell"><text class="perf-cell-label">平均</text><text class="perf-cell-value">{{ row.avg }}ms</text></view>
        <view class="perf-cell"><text class="perf-cell-label">最快</text><text class="perf-cell-value">{{ row.min }}ms</text></view>
        <view class="perf-cell"><text class="perf-cell-label">最慢</text><text class="perf-cell-value">{{ row.max }}ms</text></view>
      </view>
    </view>
    <view class="perf-clear" @click="handleClear"><text>清空样本重新测</text></view>
  </view>
</template>

<script>
import { ref } from 'vue'
import { getAllStats, clearAll } from '@/utils/perf'

const LABELS = {
  scan_to_interactive: '扫码到首屏可交互（总）',
  stage_cold_start_to_onload: '　├ 冷启动到页面开始加载',
  stage_onload_to_menu_ready: '　├ 加载到菜单数据齐全',
  stage_menu_ready_to_render: '　└ 数据齐全到渲染完成',
  menu_api: '菜单接口耗时',
  cart_open: '购物车打开耗时',
  submit_order: '提交订单耗时',
}

export default {
  setup() {
    const stats = ref(getAllStats())
    const labelOf = (metric) => LABELS[metric] || metric
    const handleClear = () => {
      clearAll()
      stats.value = getAllStats()
      uni.showToast({ title: '已清空', icon: 'none' })
    }
    return { stats, labelOf, handleClear }
  },
  onShow() {
    this.stats = getAllStats()
  },
}
</script>

<style scoped>
.perf-page { min-height: 100vh; background: #f5f7fb; padding: 24rpx; box-sizing: border-box; }
.perf-hint { font-size: 24rpx; color: #6b7280; margin-bottom: 24rpx; line-height: 1.5; }
.perf-card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 20rpx; }
.perf-card-title { font-size: 28rpx; font-weight: 700; color: #111827; margin-bottom: 16rpx; }
.perf-empty { font-size: 24rpx; color: #9ca3af; }
.perf-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16rpx; }
.perf-cell { display: flex; flex-direction: column; gap: 4rpx; }
.perf-cell-label { font-size: 22rpx; color: #9ca3af; }
.perf-cell-value { font-size: 30rpx; font-weight: 800; color: #111827; }
.perf-cell--warn .perf-cell-value { color: #ea580c; }
.perf-clear { margin-top: 12rpx; height: 88rpx; border-radius: 22rpx; background: #fff; display: flex; align-items: center; justify-content: center; text { color: #ef4444; font-size: 28rpx; font-weight: 600; } }
</style>
