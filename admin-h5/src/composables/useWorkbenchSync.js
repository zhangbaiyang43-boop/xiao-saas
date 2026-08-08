import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { getWorkbenchOrderChanges, getWorkbenchOrdersWithCursor } from '../api'
import { useOrderAlert } from './useOrderAlert'
import {
  NEW_ORDER_HIGHLIGHT_MS,
  WORKBENCH_FULL_RECONCILE_INTERVAL_MS,
  WORKBENCH_SYNC_INTERVAL_MS,
  createWorkbenchSyncCore,
  formatSyncAge,
  pendingIdsFromOrders,
} from './workbenchSyncCore'

export {
  NEW_ORDER_HIGHLIGHT_MS,
  WORKBENCH_FULL_RECONCILE_INTERVAL_MS,
  WORKBENCH_SYNC_INTERVAL_MS,
  diffNewPendingIds,
  formatSyncAge,
  pendingIdsFromOrders,
} from './workbenchSyncCore'

function unwrapWorkbenchPayload(payload) {
  const raw = payload?.data?.data ?? payload?.data ?? payload ?? []
  return Array.isArray(raw) ? raw : []
}

function readWorkbenchCursor(headers) {
  if (!headers) return null
  const value =
    headers['x-workbench-cursor'] ||
    headers['X-Workbench-Cursor'] ||
    headers.get?.('x-workbench-cursor') ||
    headers.get?.('X-Workbench-Cursor')
  return value != null && String(value).trim() ? String(value).trim() : null
}

/**
 * Fixed-terminal workbench sync: 5s delta + 60s full reconcile.
 * @param {{ dedupeKey: string, filterStatuses: string[] }} options
 */
export function useWorkbenchSync(options) {
  const dedupeKey = options.dedupeKey
  const filterStatuses = options.filterStatuses || []
  const {
    alertEnabled,
    audioNeedsUnlock,
    enableAlert,
    unlockAudio,
    ensureAlertProbed,
    playNewOrderBeep,
    isSoundReady,
  } = useOrderAlert()

  const orders = shallowRef([])
  const initialLoading = ref(false)
  const backgroundSyncing = ref(false)
  const syncFailed = ref(false)
  const networkOnline = ref(typeof navigator === 'undefined' ? true : navigator.onLine !== false)
  const lastSuccessfulSyncAt = ref(null)
  const highlightTick = ref(0)
  const syncAgeTick = ref(0)

  let core = null
  let ageTimer = null

  function applyState(state) {
    orders.value = state.orders
    initialLoading.value = state.initialLoading
    backgroundSyncing.value = state.backgroundSyncing
    syncFailed.value = state.syncFailed
    networkOnline.value = state.networkOnline
    lastSuccessfulSyncAt.value = state.lastSuccessfulSyncAt
    highlightTick.value += 1
  }

  function isHighlighted(id) {
    highlightTick.value
    return core ? core.isHighlighted(id) : false
  }

  const lastSyncLabel = computed(() => {
    syncAgeTick.value
    if (!networkOnline.value) {
      return lastSuccessfulSyncAt.value
        ? `上次同步 ${formatSyncAge(lastSuccessfulSyncAt.value)}`
        : '尚未同步'
    }
    if (syncFailed.value) return '同步失败，正在重试'
    if (!lastSuccessfulSyncAt.value) return '尚未同步'
    return `最近同步 ${formatSyncAge(lastSuccessfulSyncAt.value)}`
  })

  const soundReady = computed(() => {
    void alertEnabled.value
    void audioNeedsUnlock.value
    return isSoundReady()
  })

  async function fetchFull() {
    const res = await getWorkbenchOrdersWithCursor({
      meta: {
        dedupe: true,
        dedupeKey,
        fromPolling: Boolean(core?.getState()?.hasBaseline),
        page: 'workbench',
        rawResponse: true,
      },
    })
    const body = res?.data
    const list = unwrapWorkbenchPayload(body)
    const cursor = readWorkbenchCursor(res?.headers)
    return { orders: list, cursor }
  }

  async function fetchChanges(cursor) {
    const res = await getWorkbenchOrderChanges(
      { cursor },
      {
        meta: {
          dedupe: true,
          dedupeKey: `${dedupeKey}:changes`,
          fromPolling: true,
          page: 'workbench',
        },
      },
    )
    const data = res?.data?.data || res?.data || res || {}
    return {
      items: Array.isArray(data.items) ? data.items : [],
      removed_ids: Array.isArray(data.removed_ids) ? data.removed_ids : [],
      next_cursor: data.next_cursor != null ? String(data.next_cursor) : cursor,
      has_more: Boolean(data.has_more),
      bootstrap: Boolean(data.bootstrap),
    }
  }

  function filterOrders(raw) {
    return raw.filter((o) => filterStatuses.includes(o.status))
  }

  function onVisibility() {
    if (!core) return
    core.setVisible(document.visibilityState === 'visible')
  }

  function onFocus() {
    if (!core) return
    if (document.visibilityState === 'visible') core.syncNow()
  }

  function onOnline() {
    core?.setOnline(true)
  }

  function onOffline() {
    core?.setOnline(false)
  }

  function startAgeTicker() {
    stopAgeTicker()
    ageTimer = setInterval(() => {
      syncAgeTick.value += 1
    }, 1000)
  }

  function stopAgeTicker() {
    if (ageTimer != null) {
      clearInterval(ageTimer)
      ageTimer = null
    }
  }

  onMounted(() => {
    ensureAlertProbed()
    core = createWorkbenchSyncCore({
      fetchFull,
      fetchChanges,
      filterOrders,
      playSound: () => {
        playNewOrderBeep()
      },
      intervalMs: WORKBENCH_SYNC_INTERVAL_MS,
      fullIntervalMs: WORKBENCH_FULL_RECONCILE_INTERVAL_MS,
      highlightMs: NEW_ORDER_HIGHLIGHT_MS,
      onChange: applyState,
    })
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('focus', onFocus)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    startAgeTicker()
    core.setOnline(navigator.onLine !== false)
    core.setVisible(document.visibilityState !== 'hidden')
    core.start()
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('focus', onFocus)
    window.removeEventListener('online', onOnline)
    window.removeEventListener('offline', onOffline)
    stopAgeTicker()
    core?.stop()
    core = null
  })

  function syncNow() {
    return core ? core.syncNow() : Promise.resolve({ skipped: true, reason: 'not_started' })
  }

  function enableSound() {
    if (audioNeedsUnlock.value && alertEnabled.value) {
      unlockAudio()
      return
    }
    enableAlert()
  }

  return {
    orders,
    initialLoading,
    backgroundSyncing,
    syncFailed,
    networkOnline,
    lastSuccessfulSyncAt,
    lastSyncLabel,
    alertEnabled,
    audioNeedsUnlock,
    soundReady,
    enableSound,
    unlockAudio,
    enableAlert,
    isHighlighted,
    syncNow,
    pendingCount: computed(() => pendingIdsFromOrders(orders.value).size),
  }
}
