<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">后厨工作台</div>
        <div class="wb-sub">{{ displayName || '厨房' }} · 做什么菜</div>
      </div>
      <a-button size="small" @click="load">刷新</a-button>
    </div>

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

    <div v-if="loading" class="wb-empty">加载中…</div>
    <div v-else-if="!visible.length" class="wb-empty">暂无订单</div>

    <div v-for="order in visible" :key="order.id" class="wb-card">
      <div class="wb-card-top">
        <div>
          <strong>{{ order.table_no || '未分桌' }}</strong>
          <span v-if="order.pickup_no"> · {{ order.pickup_no }}号桌牌</span>
        </div>
        <span class="wait">等待 {{ waitMinutes(order.created_at) }} 分钟</span>
      </div>
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
          v-if="can('kitchen.print_reprint')"
          size="small"
          :loading="reprintId === order.id"
          @click="reprint(order)"
        >补打厨房单</a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { getWorkbenchOrders, reprintOrder, updateOrderStatus } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const can = (p) => auth.can(p)
const displayName = computed(() => auth.displayName)

const orders = ref([])
const loading = ref(false)
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

const visible = computed(() => orders.value.filter((o) => o.status === statusFilter.value))

function waitMinutes(iso) {
  if (!iso) return 0
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
}

async function load() {
  loading.value = true
  try {
    const res = await getWorkbenchOrders({ meta: { dedupe: true, dedupeKey: 'wb:kitchen' } })
    const raw = res?.data?.data || res?.data || []
    orders.value = Array.isArray(raw) ? raw.filter((o) => ['pending', 'preparing', 'done'].includes(o.status)) : []
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function setStatus(order, status) {
  busyId.value = order.id
  try {
    const res = await updateOrderStatus(order.id, status)
    if (res?.code === 200) {
      order.status = status
      message.success(status === 'preparing' ? '已开始制作' : '已完成')
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
    if (res?.code === 200) message.success(res.msg || '已提交补打')
    else message.error(res?.msg || '补打失败')
  } catch {
    message.error('补打失败')
  } finally {
    reprintId.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.wb-page { padding: 12px 12px 80px; background: #111827; min-height: 100%; color: #f9fafb; }
.wb-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
.wb-title { font-size: 22px; font-weight: 800; }
.wb-sub { font-size: 12px; color: #9ca3af; margin-top: 4px; }
.filters { display: flex; gap: 8px; margin-bottom: 12px; overflow-x: auto; }
.chip { border: 1px solid #374151; background: #1f2937; color: #e5e7eb; border-radius: 999px; padding: 6px 12px; font-size: 13px; }
.chip.active { background: #f59e0b; border-color: #f59e0b; color: #111; font-weight: 700; }
.wb-card { background: #1f2937; border-radius: 14px; padding: 16px; margin-bottom: 10px; }
.wb-card-top { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 16px; }
.wait { color: #fbbf24; font-size: 13px; }
.item-line { font-size: 20px; line-height: 1.5; margin-bottom: 4px; }
.remark { margin-top: 8px; color: #fca5a5; font-size: 15px; }
.actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.wb-empty { text-align: center; color: #9ca3af; padding: 48px 0; }
</style>
