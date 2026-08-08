<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">服务员工作台</div>
        <div class="wb-sub">{{ displayName || '服务员' }} · 订单进度</div>
      </div>
      <div class="wb-actions">
        <a-button size="small" @click="syncNow">刷新</a-button>
        <a-button size="small" @click="logout">退出</a-button>
      </div>
    </div>

    <WorkbenchSyncBar
      :network-online="networkOnline"
      :sync-failed="syncFailed"
      :sound-ready="soundReady"
      :last-sync-label="lastSyncLabel"
      @enable-sound="enableSound"
    />

    <div class="wb-stats">
      <div class="stat"><b>{{ pendingCount }}</b><span>待制作</span></div>
      <div class="stat"><b>{{ preparingCount }}</b><span>制作中</span></div>
    </div>

    <div v-if="initialLoading" class="wb-empty">加载中…</div>
    <div v-else-if="!orders.length" class="wb-empty">暂无桌台订单</div>

    <div
      v-for="order in orders"
      :key="order.id"
      class="wb-card"
    >
      <div class="wb-card-top">
        <div>
          <strong>{{ order.table_no || '未分桌' }}</strong>
          <span v-if="order.pickup_no"> · {{ order.pickup_no }}号桌牌</span>
          <span class="muted"> · #{{ order.display_order_no }}</span>
        </div>
        <a-tag>{{ statusText(order.status) }}</a-tag>
      </div>
      <div class="muted wait">已等待 {{ waitMinutes(order.created_at) }} 分钟</div>
      <div class="items">
        <div v-for="(item, idx) in order.items" :key="idx">{{ item.name }} ×{{ item.qty }}</div>
      </div>
      <div v-if="order.remark" class="remark">备注：{{ order.remark }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import WorkbenchSyncBar from '../components/WorkbenchSyncBar.vue'
import { useWorkbenchSync } from '../composables/useWorkbenchSync'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const displayName = computed(() => auth.displayName)

const {
  orders,
  initialLoading,
  syncFailed,
  networkOnline,
  lastSyncLabel,
  soundReady,
  enableSound,
  syncNow,
  pendingCount,
} = useWorkbenchSync({
  dedupeKey: 'wb:waiter',
  filterStatuses: ['pending', 'preparing'],
  alertsEnabled: false,
})

const preparingCount = computed(() => orders.value.filter((o) => o.status === 'preparing').length)

async function logout() {
  await auth.logoutCurrentDevice()
  router.replace('/login?mode=staff')
}

function statusText(s) {
  return { pending: '待制作', preparing: '制作中', done: '已完成', settled: '已结账' }[s] || s
}

function waitMinutes(iso) {
  if (!iso) return 0
  const ms = Date.now() - new Date(iso).getTime()
  return Math.max(0, Math.floor(ms / 60000))
}
</script>

<style scoped>
.wb-page { padding: 12px 12px 80px; background: #f5f5f5; min-height: 100%; }
.wb-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.wb-actions { display: flex; gap: 8px; }
.wb-title { font-size: 20px; font-weight: 700; color: #111; }
.wb-sub { font-size: 12px; color: #888; margin-top: 4px; }
.wb-stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 12px; }
.stat { background: #fff; border-radius: 12px; padding: 12px; text-align: center; }
.stat b { display: block; font-size: 22px; color: #111; }
.stat span { font-size: 12px; color: #888; }
.wb-card { background: #fff; border-radius: 14px; padding: 14px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.wb-card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.muted { color: #888; font-size: 12px; }
.wait { margin: 6px 0; }
.items { font-size: 15px; line-height: 1.6; color: #222; }
.remark { margin-top: 6px; font-size: 13px; color: #b45309; }
.wb-empty { text-align: center; color: #999; padding: 40px 0; }
</style>
