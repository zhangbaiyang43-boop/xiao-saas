<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">待发牌 {{ awaitingCount }}</div>
        <div class="wb-sub">{{ displayName || '前台' }} · 发桌牌、换桌牌</div>
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

    <div class="wb-stats">
      <div class="stat"><b>{{ awaitingCount }}</b><span>待发桌牌</span></div>
      <div class="stat"><b>{{ assignedCount }}</b><span>当前桌牌</span></div>
    </div>

    <div v-if="initialLoading" class="wb-empty">加载中…</div>
    <template v-else>
      <div class="section-title">待发桌牌 {{ awaitingCount }}</div>
      <div v-if="!awaiting.length" class="wb-empty sm">暂无待发桌牌</div>
      <div
        v-for="order in awaiting"
        :key="'a-' + order.id"
        class="wb-card"
        :class="{ 'is-new': isHighlighted(order.id) }"
      >
        <div class="wb-card-top">
          <div>
            <span v-if="isHighlighted(order.id)" class="new-badge">新</span>
            <strong>{{ order.table_no || '未分桌' }}</strong>
            <span class="muted"> · #{{ order.display_order_no }}</span>
          </div>
          <a-tag>未发</a-tag>
        </div>
        <div class="items">
          <div v-for="(item, idx) in order.items" :key="idx">{{ item.name }} ×{{ item.qty }}</div>
        </div>
        <div v-if="order.remark" class="remark">备注：{{ order.remark }}</div>
        <div class="actions">
          <a-button type="primary" size="small" @click="openPickup(order)">发桌牌</a-button>
          <a-button size="small" @click="openAssisted(order)">代客加单</a-button>
        </div>
      </div>

      <div class="section-title">当前桌牌 {{ assignedCount }}</div>
      <div v-if="!assigned.length" class="wb-empty sm">暂无已发桌牌</div>
      <div
        v-for="order in assigned"
        :key="'p-' + order.id"
        class="wb-card"
      >
        <div class="wb-card-top">
          <div>
            <strong>{{ order.table_no || '未分桌' }}</strong>
            <span> · {{ order.pickup_no }}号桌牌</span>
            <span class="muted"> · #{{ order.display_order_no }}</span>
          </div>
          <a-tag>{{ statusText(order) }}</a-tag>
        </div>
        <div class="items">
          <div v-for="(item, idx) in order.items" :key="idx">{{ item.name }} ×{{ item.qty }}</div>
        </div>
        <div class="actions">
          <a-button size="small" @click="openPickup(order)">换桌牌</a-button>
          <a-button size="small" @click="openAssisted(order)">代客加单</a-button>
        </div>
      </div>
    </template>

    <PickupNoPicker
      v-model:open="pickupOpen"
      :count="pickupCount"
      :occupied="pickupOccupied"
      :current="pickupCurrent"
      :dining-session-id="pickupSessionId"
      :loading="pickupLoading"
      :submitting="pickupSaving"
      @select="handlePickupSelect"
    />

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
import { getPickupNoStatus, updateOrderPickupNo } from '../api'
import AssistedOrderSheet from '../components/AssistedOrderSheet.vue'
import PickupNoPicker from '../components/PickupNoPicker.vue'
import WorkbenchSyncBar from '../components/WorkbenchSyncBar.vue'
import { needsPickupIdsFromOrders, useWorkbenchSync } from '../composables/useWorkbenchSync'
import { useAuthStore } from '../stores/auth'
import { formatOrderStatusText } from '../utils/orderStatusText'
import { canReplacePickup, needsPickup, pickupConflictToast } from '../utils/pickupNoUi'
import { getSession } from '../utils/session'

const router = useRouter()
const auth = useAuthStore()
const displayName = computed(() => auth.displayName)
const shopId = computed(() => getSession().tenantId || '')
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
  dedupeKey: 'wb:frontdesk',
  filterStatuses: ['pending', 'preparing'],
  alertIdsFromOrders: needsPickupIdsFromOrders,
})

const awaiting = computed(() => orders.value.filter((o) => needsPickup(o)))
const assigned = computed(() => orders.value.filter((o) => canReplacePickup(o)))
const awaitingCount = computed(() => awaiting.value.length)
const assignedCount = computed(() => assigned.value.length)

const pickupOpen = ref(false)
const pickupTarget = ref(null)
const pickupCount = ref(30)
const pickupOccupied = ref([])
const pickupLoading = ref(false)
const pickupSaving = ref(false)
const pickupCurrent = computed(() => pickupTarget.value?.pickup_no || '')
const pickupSessionId = computed(() => pickupTarget.value?.dining_session_id || null)

async function logout() {
  await auth.logoutCurrentDevice()
  router.replace('/login?mode=staff')
}

function statusText(order) {
  // done = 厨房出餐完成；端上桌是独立的 served_at 环节，没上菜前不说"已上餐"
  if (order?.status === 'done') return order?.served_at ? '已上餐' : '已出餐'
  return formatOrderStatusText(order?.status, order?.status_text)
}

async function refreshOccupied() {
  pickupLoading.value = true
  try {
    const status = await getPickupNoStatus()
    if (status?.code === 200 && status.data) {
      pickupCount.value = Number(status.data.count || 30)
      pickupOccupied.value = Array.isArray(status.data.occupied) ? status.data.occupied : []
    }
  } catch {
    /* picker still usable with last occupied */
  } finally {
    pickupLoading.value = false
  }
}

async function openPickup(order) {
  pickupTarget.value = order
  pickupOpen.value = true
  await refreshOccupied()
}

async function handlePickupSelect(no) {
  if (!pickupTarget.value) return
  const value = String(no || '').trim()
  if (!value) {
    message.warning('请选择桌牌号')
    return
  }
  pickupSaving.value = true
  try {
    const res = await updateOrderPickupNo(pickupTarget.value.id, value)
    if (res?.code === 200) {
      message.success(pickupTarget.value.pickup_no ? '桌牌已更换' : '桌牌已发放')
      pickupOpen.value = false
      await syncNow()
    } else {
      message.error(res?.msg || pickupConflictToast(value))
      await refreshOccupied()
    }
  } catch (e) {
    message.error(e?.response?.data?.msg || pickupConflictToast(value))
    await refreshOccupied()
  } finally {
    pickupSaving.value = false
  }
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
.section-title { font-size: 14px; font-weight: 700; color: #333; margin: 14px 0 8px; }
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
.items { font-size: 15px; line-height: 1.6; color: #222; margin-top: 6px; }
.remark { margin-top: 6px; font-size: 13px; color: #b45309; }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.wb-empty { text-align: center; color: #999; padding: 40px 0; }
.wb-empty.sm { padding: 16px 0 8px; font-size: 13px; }
</style>
