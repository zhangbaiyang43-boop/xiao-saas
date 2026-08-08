<template>
  <div v-if="tabs.length" class="bottom-tabbar">
    <div
      v-for="tab in tabs"
      :key="tab.path"
      class="tab-item"
      :class="{ active: isActive(tab.path) }"
      @click="router.push(tab.path)"
    >
      <a-badge :count="tab.badge || 0" :offset="[6, -2]" size="small">
        <component :is="tab.icon" class="tab-icon" />
      </a-badge>
      <span>{{ tab.label }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeOutlined,
  OrderedListOutlined,
  AppstoreOutlined,
  EllipsisOutlined,
  FireOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { getOrders, getWorkbenchOrders } from '../api'
import pollingManager from '../utils/pollingManager'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const pendingCount = ref(0)

function isActive(path) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(path + '/')
}

async function fetchPending(pollMeta = {}) {
  try {
    if (auth.isOwner) {
      const res = await getOrders(
        { date_str: 'today' },
        { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'admin:orders:today' } },
      )
      const raw = res?.data?.data || res?.data || []
      if (Array.isArray(raw)) pendingCount.value = raw.filter((o) => o.status === 'pending').length
    } else if (auth.can('order.view_fulfillment')) {
      const res = await getWorkbenchOrders({
        meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'wb:pending-badge' },
      })
      const raw = res?.data?.data || res?.data || []
      if (Array.isArray(raw)) {
        if (auth.role === 'frontdesk') {
          pendingCount.value = raw.filter(
            (o) => (o.can_assign_pickup_no || o.canAssignPickupNo) && !o.pickup_no,
          ).length
        } else {
          pendingCount.value = raw.filter((o) => o.status === 'pending').length
        }
      }
    }
  } catch {}
}

const tabs = computed(() => {
  if (auth.role === 'frontdesk') {
    return [
      { path: '/frontdesk', label: '前台', icon: OrderedListOutlined, badge: pendingCount.value },
      { path: '/more', label: '我的', icon: UserOutlined, badge: 0 },
    ]
  }
  if (auth.role === 'waiter') {
    return [
      { path: '/waiter', label: '工作台', icon: OrderedListOutlined, badge: pendingCount.value },
      { path: '/more', label: '我的', icon: UserOutlined, badge: 0 },
    ]
  }
  if (auth.role === 'kitchen') {
    return [
      { path: '/kitchen', label: '厨房', icon: FireOutlined, badge: pendingCount.value },
      { path: '/more', label: '我的', icon: UserOutlined, badge: 0 },
    ]
  }
  return [
    { path: '/', label: '今日', icon: HomeOutlined, badge: 0 },
    { path: '/orders', label: '接单', icon: OrderedListOutlined, badge: pendingCount.value },
    { path: '/menu', label: '菜单', icon: AppstoreOutlined, badge: 0 },
    { path: '/more', label: '更多', icon: EllipsisOutlined, badge: 0 },
  ]
})

function shouldPollPending() {
  if (auth.role === 'frontdesk') return route.path !== '/frontdesk'
  if (auth.role === 'waiter') return route.path !== '/waiter'
  if (auth.role === 'kitchen') return route.path !== '/kitchen'
  return route.path !== '/' && !route.path.startsWith('/orders')
}

function syncPendingPolling() {
  if (shouldPollPending()) {
    pollingManager.start('tabbar:orders:pending', {
      task: fetchPending,
      interval: 60000,
      hiddenInterval: 120000,
      idleInterval: 120000,
    })
  } else {
    pollingManager.stop('tabbar:orders:pending')
  }
}

onMounted(syncPendingPolling)
watch(() => route.path, syncPendingPolling)
watch(() => auth.role, syncPendingPolling)
onBeforeUnmount(() => pollingManager.stop('tabbar:orders:pending'))
</script>
