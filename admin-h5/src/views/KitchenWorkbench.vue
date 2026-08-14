<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">待制作 {{ pendingCount }}</div>
        <div class="wb-sub">{{ displayName || '厨房' }} · 接单、制作完成</div>
      </div>
      <div class="wb-actions">
        <a-button size="small" @click="syncNow">刷新</a-button>
        <a-button size="small" @click="logout">退出</a-button>
      </div>
    </div>

    <WorkbenchSyncBar
      variant="dark"
      :network-online="networkOnline"
      :sync-failed="syncFailed"
      :sound-ready="soundReady"
      :last-sync-label="lastSyncLabel"
      @enable-sound="enableSound"
    />

    <div v-if="printIssueCount > 0" class="print-anomaly">打印异常 {{ printIssueCount }}</div>

    <div class="filters">
      <button
        v-for="f in filters"
        :key="f.val"
        type="button"
        class="chip"
        :class="{ active: statusFilter === f.val }"
        @click="statusFilter = f.val"
      >{{ f.label }} {{ counts[f.val] || 0 }}</button>
    </div>

    <div v-if="initialLoading" class="wb-empty">加载中…</div>
    <div v-else-if="!visible.length" class="wb-empty">暂无订单</div>

    <div
      v-for="order in visible"
      :key="order.id"
      class="wb-card"
      :class="{ 'is-new': isHighlighted(order.id) }"
    >
      <div class="wb-card-top">
        <div>
          <span v-if="isHighlighted(order.id)" class="new-badge">新</span>
          <strong>{{ order.table_no || '未分桌' }}</strong>
          <span v-if="order.pickup_no"> · {{ order.pickup_no }}号桌牌</span>
          <span
            v-if="order.print_issue === 'failed'"
            class="print-badge print-badge--failed"
          >打印失败</span>
          <span
            v-else-if="order.print_issue === 'unknown'"
            class="print-badge print-badge--unknown"
          >打印状态未知</span>
          <span
            v-else-if="order.print_issue === 'waiting_pickup'"
            class="print-badge print-badge--waiting"
          >等待桌牌后打印</span>
          <span
            v-else-if="order.print_status === 'SUCCESS'"
            class="print-ok"
          >已提交打印</span>
        </div>
        <span class="wait">等待 {{ waitMinutes(order.created_at) }} 分钟</span>
      </div>
      <div
        v-if="order.print_issue === 'failed' || order.print_issue === 'unknown'"
        class="print-detail"
      >{{ printDiagnostic(order) }}</div>
      <div class="items">
        <div v-for="(item, idx) in order.items" :key="idx" class="item-line">
          <b>{{ item.name }}</b> ×{{ item.qty }}
        </div>
      </div>
      <div v-if="order.remark" class="remark">{{ order.remark }}</div>
      <div class="actions">
        <a-button
          v-if="order.status === 'pending' && can('order.accept')"
          type="primary"
          size="small"
          :loading="busyId === order.id"
          @click="setStatus(order, 'preparing')"
        >开始制作</a-button>
        <a-button
          v-if="order.status === 'preparing' && can('order.complete')"
          type="primary"
          size="small"
          :loading="busyId === order.id"
          @click="setStatus(order, 'done')"
        >完成</a-button>
        <a-button
          v-if="can('kitchen.print_reprint') && order.can_reprint"
          size="small"
          :loading="reprintId === order.id"
          @click="reprint(order)"
        >补打厨房单</a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { reprintOrder, updateOrderStatus } from '../api'
import WorkbenchSyncBar from '../components/WorkbenchSyncBar.vue'
import { useWorkbenchSync } from '../composables/useWorkbenchSync'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const can = (p) => auth.can(p)
const displayName = computed(() => auth.displayName)

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
  dedupeKey: 'wb:kitchen',
  filterStatuses: ['pending', 'preparing', 'done'],
})

const busyId = ref('')
const reprintId = ref('')
const statusFilter = ref('pending')
const filters = [
  { label: '待制作', val: 'pending' },
  { label: '制作中', val: 'preparing' },
  { label: '已完成', val: 'done' },
]

const counts = computed(() => ({
  pending: orders.value.filter((o) => o.status === 'pending').length,
  preparing: orders.value.filter((o) => o.status === 'preparing').length,
  done: orders.value.filter((o) => o.status === 'done').length,
}))
const pendingCount = computed(() => counts.value.pending)

const printIssueCount = computed(() =>
  orders.value.filter((o) => o.print_issue === 'failed' || o.print_issue === 'unknown').length,
)

const visible = computed(() => orders.value.filter((o) => o.status === statusFilter.value))

function printDiagnostic(order) {
  const route = [order.print_provider, order.print_printer_identifier].filter(Boolean).join(' / ')
  const attempt = order.print_last_attempt_at
    ? new Date(order.print_last_attempt_at).toLocaleString('zh-CN', { hour12: false })
    : '暂无时间'
  const manual = Number(order.manual_reprint_count || 0)
    ? ` · 补打${order.manual_reprint_count}次(${order.manual_reprint_last_status || '处理中'})`
    : ''
  return `${order.print_error_code || '未返回错误码'} · ${attempt}${route ? ` · ${route}` : ''}${manual}`
}

async function logout() {
  await auth.logoutCurrentDevice()
  router.replace('/login?mode=staff')
}

function waitMinutes(iso) {
  if (!iso) return 0
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
}

async function setStatus(order, status) {
  busyId.value = order.id
  try {
    const res = await updateOrderStatus(order.id, status)
    if (res?.code === 200) {
      message.success(status === 'preparing' ? '已开始制作' : '已完成')
      await syncNow()
    } else message.error(res?.msg || '操作失败')
  } catch {
    message.error('操作失败')
  } finally {
    busyId.value = ''
  }
}

async function reprint(order) {
  reprintId.value = order.id
  try {
    const res = await reprintOrder(order.id, 'kitchen')
    if (res?.code === 200) {
      message.success(res.msg || '已提交补打')
      await syncNow()
    } else message.error(res?.msg || '补打失败')
  } catch {
    message.error('补打失败')
  } finally {
    reprintId.value = ''
  }
}
</script>

<style scoped>
.wb-page { padding: 12px 12px 80px; background: #111827; min-height: 100%; color: #f9fafb; }
.print-detail { margin: -2px 0 8px; color: #fca5a5; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
.wb-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
.wb-actions { display: flex; gap: 8px; }
.wb-title { font-size: 22px; font-weight: 800; }
.wb-sub { font-size: 12px; color: #9ca3af; margin-top: 4px; }
.filters { display: flex; gap: 8px; margin-bottom: 12px; overflow-x: auto; }
.chip { border: 1px solid #374151; background: #1f2937; color: #e5e7eb; border-radius: 999px; padding: 6px 12px; font-size: 13px; }
.chip.active { background: #f59e0b; border-color: #f59e0b; color: #111; font-weight: 700; }
.wb-card { background: #1f2937; border-radius: 14px; padding: 16px; margin-bottom: 10px; border: 1px solid transparent; }
.wb-card.is-new { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245, 158, 11, .25); }
.new-badge {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 6px;
  background: #f59e0b;
  color: #111;
  font-size: 11px;
  font-weight: 800;
  vertical-align: middle;
}
.print-anomaly {
  margin-bottom: 10px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #7f1d1d;
  color: #fecaca;
  font-size: 13px;
  font-weight: 700;
}
.wb-card-top { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 16px; }
.wait { color: #fbbf24; font-size: 13px; }
.print-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  vertical-align: middle;
}
.print-badge--failed { background: #7f1d1d; color: #fecaca; }
.print-badge--unknown { background: #78350f; color: #fde68a; }
.print-badge--waiting { background: #1e3a5f; color: #93c5fd; }
.print-ok { margin-left: 8px; font-size: 11px; color: #9ca3af; font-weight: 500; }
.item-line { font-size: 20px; line-height: 1.5; margin-bottom: 4px; }
.remark { margin-top: 8px; color: #fca5a5; font-size: 15px; }
.actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.wb-empty { text-align: center; color: #9ca3af; padding: 48px 0; }
</style>
