<template>
  <div class="wb-page">
    <div class="wb-header">
      <div>
        <div class="wb-title">服务员工作台</div>
        <div class="wb-sub">{{ displayName || '前厅履约' }} · 下一件要处理什么</div>
      </div>
      <div class="wb-actions">
        <a-button size="small" @click="load">刷新</a-button>
        <a-button size="small" @click="logout">退出</a-button>
      </div>
    </div>

    <div class="wb-stats">
      <div class="stat"><b>{{ pendingCount }}</b><span>待接单</span></div>
      <div class="stat"><b>{{ preparingCount }}</b><span>备餐中</span></div>
    </div>

    <div v-if="loading" class="wb-empty">加载中…</div>
    <div v-else-if="!orders.length" class="wb-empty">暂无待处理订单</div>

    <div v-for="order in orders" :key="order.id" class="wb-card">
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
      <div class="actions">
        <a-button
          v-if="order.status === 'pending' && can('order.accept')"
          type="primary"
          size="small"
          :loading="busyId === order.id"
          @click="accept(order)"
        >接单</a-button>
        <a-button
          v-if="can('pickup.assign') && (order.can_assign_pickup_no || order.pickup_no)"
          size="small"
          @click="openPickup(order)"
        >{{ order.pickup_no ? '换桌牌' : '发桌牌' }}</a-button>
      </div>
    </div>

    <a-modal v-model:open="pickupOpen" title="桌牌号码" @ok="submitPickup" :confirmLoading="pickupSaving">
      <a-input v-model:value="pickupNo" placeholder="例如 8" maxlength="8" />
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { getWorkbenchOrders, updateOrderPickupNo, updateOrderStatus } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const can = (p) => auth.can(p)
const displayName = computed(() => auth.displayName)

async function logout() {
  await auth.logoutCurrentDevice()
  router.replace('/login?mode=staff')
}

const orders = ref([])
const loading = ref(false)
const busyId = ref('')
const pickupOpen = ref(false)
const pickupTarget = ref(null)
const pickupNo = ref('')
const pickupSaving = ref(false)

const pendingCount = computed(() => orders.value.filter((o) => o.status === 'pending').length)
const preparingCount = computed(() => orders.value.filter((o) => o.status === 'preparing').length)

function statusText(s) {
  return { pending: '待接单', preparing: '备餐中', done: '已完成', settled: '已结账' }[s] || s
}

function waitMinutes(iso) {
  if (!iso) return 0
  const ms = Date.now() - new Date(iso).getTime()
  return Math.max(0, Math.floor(ms / 60000))
}

async function load() {
  loading.value = true
  try {
    const res = await getWorkbenchOrders({ meta: { dedupe: true, dedupeKey: 'wb:waiter' } })
    const raw = res?.data?.data || res?.data || []
    // Waiter has no finance.settle — only show actionable fulfillment jobs.
    orders.value = Array.isArray(raw) ? raw.filter((o) => ['pending', 'preparing'].includes(o.status)) : []
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function accept(order) {
  busyId.value = order.id
  try {
    const res = await updateOrderStatus(order.id, 'preparing')
    if (res?.code === 200) {
      order.status = 'preparing'
      message.success('已接单')
    } else message.error(res?.msg || '接单失败')
  } catch {
    message.error('接单失败')
  } finally {
    busyId.value = ''
  }
}

function openPickup(order) {
  pickupTarget.value = order
  pickupNo.value = order.pickup_no || ''
  pickupOpen.value = true
}

async function submitPickup() {
  if (!pickupTarget.value) return
  const no = String(pickupNo.value || '').trim()
  if (!no) {
    message.warning('请输入桌牌号')
    return
  }
  pickupSaving.value = true
  try {
    const res = await updateOrderPickupNo(pickupTarget.value.id, no)
    if (res?.code === 200) {
      message.success('桌牌已更新')
      pickupOpen.value = false
      await load()
    } else message.error(res?.msg || '桌牌更新失败')
  } catch (e) {
    message.error(e?.response?.data?.msg || '桌牌更新失败')
  } finally {
    pickupSaving.value = false
  }
}

onMounted(load)
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
.actions { display: flex; gap: 8px; margin-top: 12px; }
.wb-empty { text-align: center; color: #999; padding: 40px 0; }
</style>
