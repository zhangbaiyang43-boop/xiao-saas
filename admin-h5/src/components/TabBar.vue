﻿﻿﻿﻿﻿<template>
  <div class="bottom-tabbar">
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
import { HomeOutlined, OrderedListOutlined, AppstoreOutlined, EllipsisOutlined } from '@ant-design/icons-vue'
import { getOrders } from '../api'
import pollingManager from '../utils/pollingManager'

const router = useRouter()
const route = useRoute()
const pendingCount = ref(0)

function isActive(path) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(path + '/')
}

async function fetchPending(pollMeta = {}) {
  try {
    const res = await getOrders({ date_str: 'today' }, { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'admin:orders:today' } })
    const raw = res?.data?.data || res?.data || []
    if (Array.isArray(raw)) pendingCount.value = raw.filter(o => o.status === 'pending').length
  } catch {}
}

const tabs = computed(() => [
  { path: '/', label: '今日', icon: HomeOutlined, badge: 0 },
  { path: '/orders', label: '接单', icon: OrderedListOutlined, badge: pendingCount.value },
  { path: '/menu', label: '菜单', icon: AppstoreOutlined, badge: 0 },
  { path: '/more', label: '更多', icon: EllipsisOutlined, badge: 0 },
])

function shouldPollPending() {
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
onBeforeUnmount(() => pollingManager.stop('tabbar:orders:pending'))
</script>

