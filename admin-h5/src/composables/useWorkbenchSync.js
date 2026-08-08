import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { getWorkbenchOrders } from '../api'
import { useOrderAlert } from './useOrderAlert'
import {
  NEW_ORDER_HIGHLIGHT_MS,
  WORKBENCH_SYNC_INTERVAL_MS,
  createWorkbenchSyncCore,
  formatSyncAge,
  pendingIdsFromOrders,
} from './workbenchSyncCore'

export {
  NEW_ORDER_HIGHLIGHT_MS,
  WORKBENCH_SYNC_INTERVAL_MS,
  diffNewPendingIds,
  formatSyncAge,
  pendingIdsFromOrders,
} from './workbenchSyncCore'

function unwrapWorkbenchPayload(res) {
  const raw = res?.data?.data || res?.data || res || []
  return Array.isArray(raw) ? raw : []
}

/**
 * Fixed-terminal workbench sync: visible 5s DB snapshot, visibility/online immediate sync.
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

  async function fetchOrders() {
    const res = await getWorkbenchOrders({
      meta: {
        dedupe: true,
        dedupeKey,
        fromPolling: Boolean(core?.getState()?.hasBaseline),
        page: 'workbench',
      },
    })
    return unwrapWorkbenchPayload(res)
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
      fetchOrders,
      filterOrders,
      playSound: () => {
        playNewOrderBeep()
      },
      intervalMs: WORKBENCH_SYNC_INTERVAL_MS,
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
