<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">待上菜 {{ waitingCount }}</div>
        <div class="wb-sub">{{ displayName || '服务员' }} · 确认上菜即完成</div>
      </div>
      <div class="wb-actions">
        <a-button size="small" @click="openAssisted()">代客加单</a-button>
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
        >确认已上菜</a-button>
        <a-button size="small" block class="ao-entry" @click="openAssisted(order)">代客加单</a-button>
      </div>
      <div v-if="failId === order.id" class="fail">上菜确认失败，请重试</div>
    </div>

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
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { serveOrder } from '../api'
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

async function logout() {
  await auth.logoutCurrentDevice()
  router.replace('/login?mode=staff')
}

async function confirmServed(order) {
  if (!order?.id || busyId.value === order.id) return
  busyId.value = order.id
  failId.value = ''
  try {
    const res = await serveOrder(order.id)
    if (res?.code === 200) {
      message.success('已确认上菜')
      await syncNow()
    } else {
      failId.value = order.id
      message.error(res?.msg || '确认失败，请重试')
    }
  } catch {
    failId.value = order.id
    message.error('确认失败，请重试')
  } finally {
    busyId.value = ''
  }
}
</script>

<style scoped>
.wb-page { padding: 12px 12px 80px; background: #f5f5f5; min-height: 100%; }
.wb-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.wb-actions { display: flex; gap: 8px; }
.wb-title { font-size: 22px; font-weight: 800; color: #111; }
.wb-sub { font-size: 12px; color: #888; margin-top: 4px; }
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
.ao-entry { color: #666; }
.fail { margin-top: 8px; font-size: 12px; color: #dc2626; }
.wb-empty { text-align: center; color: #999; padding: 48px 0; }
</style>
