<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">待上菜 {{ waitingCount }}</div>
        <div class="wb-sub">{{ displayName || '服务员' }} · 确认上菜即完成</div>
      </div>
      <div class="wb-actions">
        <a-button size="small" @click="openAssisted()">顾客加菜</a-button>
        <details class="more-menu">
          <summary>⋯</summary>
          <button type="button" @click="logout">退出登录</button>
        </details>
      </div>
    </div>

    <div class="sync-line">
      <WorkbenchSyncBar
        class="sync-bar"
        :network-online="networkOnline"
        :sync-failed="syncFailed"
        :sound-ready="soundReady"
        :last-sync-label="lastSyncLabel"
        @enable-sound="enableSound"
      />
      <button type="button" class="sync-link" :disabled="initialLoading" @click="syncNow">↻</button>
    </div>

    <div v-if="initialLoading" class="wb-empty">加载中…</div>
    <div v-else-if="!queue.length" class="wb-empty">暂无待上菜</div>

    <div
      v-for="order in queue"
      :key="order.id"
      class="wb-card"
      :class="{ 'is-new': isHighlighted(order.id) }"
    >
      <div class="wb-card-top">
        <div>
          <span v-if="isHighlighted(order.id)" class="new-badge">新</span>
          <strong>{{ order.table_no || '未分桌' }}</strong>
          <span v-if="order.pickup_no"> · {{ order.pickup_no }}号桌牌</span>
          <span class="muted"> · #{{ order.display_order_no }}</span>
        </div>
      </div>
      <div class="items">
        <div v-for="(item, idx) in order.items" :key="idx">{{ item.name }} ×{{ item.qty }}</div>
      </div>
      <div v-if="order.remark" class="remark">备注：{{ order.remark }}</div>
      <div v-if="order.staff_note" class="remark staff">厨房/代点：{{ order.staff_note }}</div>
      <div class="actions">
        <a-button
          type="primary"
          size="large"
          block
          :loading="busyId === order.id"
          :disabled="busyId === order.id"
          @click="confirmServed(order)"
        >{{ busyId === order.id ? '正在确认…' : '确认已上菜' }}</a-button>
      </div>
      <div v-if="failId === order.id" class="fail">上菜确认失败，请重试</div>
    </div>

    <section v-if="recentServed.length" class="recent">
      <div class="recent-title">最近已上菜</div>
      <div v-for="item in recentServed.slice(0, 3)" :key="item.order_id" class="recent-row">
        <div>
          <strong>{{ servingLabel(item) }}</strong>
          <div class="recent-items">{{ itemSummary(item) }}</div>
        </div>
        <span class="recent-time">{{ timeLabel(item.served_at) }}</span>
      </div>
    </section>

    <AssistedOrderSheet
      v-model:open="assistedOpen"
      :shop-id="shopId"
      :preset-table-no="assistedTable"
      :preset-dining-session-id="assistedSessionId"
      @success="onAssistedSuccess"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { getRecentServedByMe, serveOrder } from '../api'
import AssistedOrderSheet from '../components/AssistedOrderSheet.vue'
import WorkbenchSyncBar from '../components/WorkbenchSyncBar.vue'
import { waitingToServeIdsFromOrders, useWorkbenchSync } from '../composables/useWorkbenchSync'
import { useAuthStore } from '../stores/auth'
import { getSession } from '../utils/session'

const router = useRouter()
const auth = useAuthStore()
const displayName = computed(() => auth.displayName)
const shopId = computed(() => getSession().tenant_id || '')
const assistedOpen = ref(false)
const assistedTable = ref('')
const assistedSessionId = ref('')
const recentServed = ref([])

function openAssisted(order) {
  assistedTable.value = order?.table_no || ''
  assistedSessionId.value = order?.dining_session_id || ''
  assistedOpen.value = true
}

async function onAssistedSuccess() {
  await syncNow()
}

const {
  orders,
  initialLoading,
  syncFailed,
  networkOnline,
  lastSyncLabel,
  soundReady,
  enableSound,
  isHighlighted,
  syncNow,
} = useWorkbenchSync({
  dedupeKey: 'wb:waiter',
  filterStatuses: ['done'],
  alertIdsFromOrders: waitingToServeIdsFromOrders,
  alertsEnabled: true,
})

const queue = computed(() =>
  orders.value.filter((o) => o.status === 'done' && !o.served_at),
)
const waitingCount = computed(() => queue.value.length)
const busyId = ref('')
const failId = ref('')

function servingLabel(order) {
  const pickup = order?.pickup_no ? `${order.pickup_no}号桌牌` : ''
  const table = order?.table_no ? `${order.table_no}号桌` : ''
  return pickup || table || '未分桌'
}

function itemSummary(order) {
  const items = Array.isArray(order?.items) ? order.items : []
  if (!items.length) return '菜品已上齐'
  if (items.length === 1) return `${items[0].name} ×${items[0].qty}`
  const count = items.reduce((sum, item) => sum + Number(item.qty || 0), 0)
  return `共 ${count || items.length} 个菜`
}

function timeLabel(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

async function loadRecentServed() {
  try {
    const res = await getRecentServedByMe({ limit: 10 })
    const rows = res?.data?.data || res?.data || []
    recentServed.value = Array.isArray(rows) ? rows : []
  } catch {
    recentServed.value = []
  }
}

async function logout() {
  await auth.logoutCurrentDevice()
  router.replace('/login?mode=staff')
}

async function confirmServed(order) {
  if (!order?.id || busyId.value === order.id) return
  if (networkOnline.value === false || navigator.onLine === false) {
    message.error('网络不可用，请联网后重试')
    return
  }
  busyId.value = order.id
  failId.value = ''
  try {
    const res = await serveOrder(order.id)
    if (res?.code === 200) {
      message.success(`✓ ${servingLabel(order)}已上菜`)
      await syncNow()
      await loadRecentServed()
    } else {
      failId.value = order.id
      message.error(res?.msg || '上菜确认失败，请重试')
    }
  } catch {
    failId.value = order.id
    message.error('上菜确认失败，请重试')
  } finally {
    busyId.value = ''
  }
}

onMounted(loadRecentServed)
</script>

<style scoped>
.wb-page { padding: 12px 12px 80px; background: #f5f5f5; min-height: 100%; }
.wb-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.wb-actions { display: flex; align-items: center; gap: 8px; }
.wb-title { font-size: 22px; font-weight: 800; color: #111; }
.wb-sub { font-size: 12px; color: #888; margin-top: 4px; }
.more-menu { position: relative; }
.more-menu summary {
  list-style: none;
  width: 28px;
  height: 24px;
  border-radius: 8px;
  border: 1px solid #e5e5e5;
  background: #fff;
  text-align: center;
  line-height: 20px;
  cursor: pointer;
}
.more-menu summary::-webkit-details-marker { display: none; }
.more-menu button {
  position: absolute;
  right: 0;
  top: 30px;
  z-index: 2;
  width: 84px;
  border: 1px solid #eee;
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
  color: #666;
  box-shadow: 0 4px 16px rgba(0,0,0,.08);
}
.sync-line { display: flex; align-items: stretch; gap: 8px; margin-bottom: 10px; }
.sync-bar { flex: 1; margin-bottom: 0; }
.sync-link {
  width: 36px;
  border: 0;
  border-radius: 10px;
  background: #fff;
  color: #666;
  font-size: 18px;
}
.wb-card { background: #fff; border-radius: 14px; padding: 14px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.04); border: 1px solid transparent; }
.wb-card.is-new { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245, 158, 11, .18); }
.new-badge {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 6px;
  background: #f59e0b;
  color: #111;
  font-size: 11px;
  font-weight: 700;
  vertical-align: middle;
}
.wb-card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.muted { color: #888; font-size: 12px; }
.items { font-size: 16px; line-height: 1.7; color: #222; margin-top: 8px; }
.remark { margin-top: 6px; font-size: 13px; color: #b45309; }
.remark.staff { color: #7c3aed; }
.actions { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
.fail { margin-top: 8px; font-size: 12px; color: #dc2626; }
.wb-empty { text-align: center; color: #999; padding: 48px 0; }
.recent { margin-top: 14px; padding: 12px 14px; border-radius: 12px; background: #fff; color: #444; }
.recent-title { font-size: 13px; font-weight: 700; color: #777; margin-bottom: 8px; }
.recent-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid #f2f2f2;
}
.recent-row:first-of-type { border-top: 0; }
.recent-row strong { font-size: 14px; color: #333; }
.recent-items { margin-top: 2px; color: #777; font-size: 13px; }
.recent-time { flex: 0 0 auto; color: #999; font-size: 12px; }
</style>
