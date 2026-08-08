/** Workbench auto-sync core — Order DB is source of truth; polling only triggers sync. */

export const WORKBENCH_SYNC_INTERVAL_MS = 5000
export const NEW_ORDER_HIGHLIGHT_MS = 8000

export function pendingIdsFromOrders(orders) {
  const ids = new Set()
  for (const o of orders || []) {
    if (o && o.status === 'pending' && o.id != null) {
      ids.add(String(o.id))
    }
  }
  return ids
}

/** New pending IDs in `current` that are not in `known`. Uses string IDs only. */
export function diffNewPendingIds(known, current) {
  const news = []
  for (const id of current) {
    if (!known.has(id)) news.push(id)
  }
  return news
}

export function formatSyncAge(at, now = Date.now()) {
  if (!at) return '尚未同步'
  const sec = Math.max(0, Math.floor((now - at) / 1000))
  if (sec < 8) return '刚刚'
  if (sec < 60) return `${sec}秒前`
  const d = new Date(at)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

/**
 * Framework-free sync controller for unit tests and useWorkbenchSync.
 *
 * @param {object} opts
 * @param {() => Promise<any[]>} opts.fetchOrders
 * @param {(raw: any[]) => any[]} opts.filterOrders
 * @param {() => void} [opts.playSound]
 * @param {() => number} [opts.now]
 * @param {number} [opts.intervalMs]
 * @param {number} [opts.highlightMs]
 * @param {(state: object) => void} [opts.onChange]
 * @param {(id: string) => void} [opts.setTimeoutFn]
 * @param {(id: any) => void} [opts.clearTimeoutFn]
 */
export function createWorkbenchSyncCore(opts) {
  const fetchOrders = opts.fetchOrders
  const filterOrders = opts.filterOrders
  const playSound = opts.playSound || (() => {})
  const now = opts.now || (() => Date.now())
  const intervalMs = opts.intervalMs ?? WORKBENCH_SYNC_INTERVAL_MS
  const highlightMs = opts.highlightMs ?? NEW_ORDER_HIGHLIGHT_MS
  const onChange = opts.onChange || (() => {})
  const setTimeoutFn = opts.setTimeoutFn || ((fn, ms) => setTimeout(fn, ms))
  const clearTimeoutFn = opts.clearTimeoutFn || ((id) => clearTimeout(id))

  let orders = []
  let knownPendingIds = new Set()
  let hasBaseline = false
  let initialLoading = false
  let backgroundSyncing = false
  let inFlight = false
  let syncFailed = false
  let networkOnline = typeof navigator !== 'undefined' ? navigator.onLine !== false : true
  let lastSuccessfulSyncAt = null
  let pageVisible = true
  let running = false
  let authStopped = false
  let timer = null
  const highlightIds = new Set()
  const highlightTimers = new Map()
  let lastNewIds = []

  function emit() {
    onChange(getState())
  }

  function getState() {
    return {
      orders,
      knownPendingIds: new Set(knownPendingIds),
      hasBaseline,
      initialLoading,
      backgroundSyncing,
      inFlight,
      syncFailed,
      networkOnline,
      lastSuccessfulSyncAt,
      pageVisible,
      running,
      authStopped,
      highlightIds: new Set(highlightIds),
      lastNewIds: lastNewIds.slice(),
    }
  }

  function clearSchedule() {
    if (timer != null) {
      clearTimeoutFn(timer)
      timer = null
    }
  }

  function scheduleNext() {
    clearSchedule()
    if (!running || authStopped || !pageVisible || !networkOnline) return
    timer = setTimeoutFn(() => {
      timer = null
      sync()
    }, intervalMs)
  }

  function addHighlights(ids) {
    for (const id of ids) {
      highlightIds.add(id)
      if (highlightTimers.has(id)) {
        clearTimeoutFn(highlightTimers.get(id))
      }
      const tid = setTimeoutFn(() => {
        highlightIds.delete(id)
        highlightTimers.delete(id)
        emit()
      }, highlightMs)
      highlightTimers.set(id, tid)
    }
  }

  function clearHighlights() {
    for (const tid of highlightTimers.values()) clearTimeoutFn(tid)
    highlightTimers.clear()
    highlightIds.clear()
  }

  async function sync() {
    if (!running || authStopped) return { skipped: true, reason: 'stopped' }
    if (inFlight) return { skipped: true, reason: 'in_flight' }

    inFlight = true
    if (!hasBaseline) initialLoading = true
    else backgroundSyncing = true
    emit()

    try {
      const raw = await fetchOrders()
      const list = filterOrders(Array.isArray(raw) ? raw : [])
      const currentPending = pendingIdsFromOrders(list)
      let newIds = []
      if (hasBaseline) {
        newIds = diffNewPendingIds(knownPendingIds, currentPending)
      }

      orders = list
      knownPendingIds = currentPending
      hasBaseline = true
      lastSuccessfulSyncAt = now()
      syncFailed = false
      lastNewIds = newIds

      if (newIds.length) {
        addHighlights(newIds)
        try {
          playSound()
        } catch {
          /* sound must never break sync */
        }
      }

      emit()
      return { ok: true, newIds, orders: list }
    } catch (err) {
      const status = err?.response?.status
      if (status === 401 || status === 403) {
        authStopped = true
        clearSchedule()
      }
      syncFailed = true
      lastNewIds = []
      emit()
      return { ok: false, error: err }
    } finally {
      inFlight = false
      initialLoading = false
      backgroundSyncing = false
      emit()
      scheduleNext()
    }
  }

  function setVisible(visible) {
    pageVisible = Boolean(visible)
    if (!running) {
      emit()
      return
    }
    if (pageVisible) {
      emit()
      sync()
    } else {
      clearSchedule()
      emit()
    }
  }

  function setOnline(online) {
    networkOnline = Boolean(online)
    if (!running) {
      emit()
      return
    }
    if (networkOnline) {
      emit()
      sync()
    } else {
      clearSchedule()
      emit()
    }
  }

  function start() {
    if (running) return
    running = true
    authStopped = false
    emit()
    sync()
  }

  function stop() {
    running = false
    clearSchedule()
    clearHighlights()
    emit()
  }

  function isHighlighted(id) {
    return highlightIds.has(String(id))
  }

  return {
    start,
    stop,
    sync,
    syncNow: sync,
    setVisible,
    setOnline,
    getState,
    isHighlighted,
    pendingIdsFromOrders,
    diffNewPendingIds,
  }
}
