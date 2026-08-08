/** Workbench auto-sync core — Order DB is source of truth; polling only triggers sync. */

export const WORKBENCH_SYNC_INTERVAL_MS = 5000
export const WORKBENCH_FULL_RECONCILE_INTERVAL_MS = 60000
export const WORKBENCH_DELTA_MAX_PAGES = 5
export const WORKBENCH_DELTA_FAIL_FALLBACK = 3
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

/** Frontdesk alert set: assignable and still missing pickup_no. */
export function needsPickupIdsFromOrders(orders) {
  const ids = new Set()
  for (const o of orders || []) {
    if (!o || o.id == null) continue
    const can = o.can_assign_pickup_no ?? o.canAssignPickupNo
    if (can && !o.pickup_no) ids.add(String(o.id))
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

export function sortOrdersFifo(orders) {
  return [...(orders || [])].sort((a, b) => {
    const ta = a?.created_at || ''
    const tb = b?.created_at || ''
    if (ta < tb) return -1
    if (ta > tb) return 1
    return String(a?.id ?? '').localeCompare(String(b?.id ?? ''))
  })
}

export function applyWorkbenchDelta(orders, items, removedIds, filterOrders) {
  const map = new Map()
  for (const o of orders || []) {
    if (o?.id != null) map.set(String(o.id), o)
  }
  for (const id of removedIds || []) {
    map.delete(String(id))
  }
  for (const item of items || []) {
    if (item?.id == null) continue
    const sid = String(item.id)
    const keep = filterOrders([item])
    if (keep.length) map.set(sid, keep[0])
    else map.delete(sid)
  }
  return sortOrdersFifo([...map.values()])
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
 * Phase 4C: 5s delta + 60s full. fetchChanges optional → legacy full-every-tick.
 *
 * @param {object} opts
 * @param {() => Promise<any[]|{orders:any[],cursor?:string}>} opts.fetchFull
 * @param {(cursor:string) => Promise<{items:any[],removed_ids:string[],next_cursor:string,has_more:boolean}>} [opts.fetchChanges]
 * @param {() => Promise<any[]>} [opts.fetchOrders] legacy alias for fetchFull
 * @param {(raw: any[]) => any[]} opts.filterOrders
 * @param {(orders: any[]) => Set<string>} [opts.alertIdsFromOrders] defaults to pendingIdsFromOrders
 * @param {boolean} [opts.alertsEnabled] default true; false disables sound + highlight diffs
 * @param {() => void} [opts.playSound]
 * @param {() => number} [opts.now]
 * @param {number} [opts.intervalMs]
 * @param {number} [opts.fullIntervalMs]
 * @param {number} [opts.highlightMs]
 * @param {(state: object) => void} [opts.onChange]
 * @param {(id: string) => void} [opts.setTimeoutFn]
 * @param {(id: any) => void} [opts.clearTimeoutFn]
 */
export function createWorkbenchSyncCore(opts) {
  const fetchFull = opts.fetchFull || opts.fetchOrders
  const fetchChanges = opts.fetchChanges || null
  const useDelta = typeof fetchChanges === 'function'
  const filterOrders = opts.filterOrders
  const alertIdsFromOrders = opts.alertIdsFromOrders || pendingIdsFromOrders
  const alertsEnabled = opts.alertsEnabled !== false
  const playSound = opts.playSound || (() => {})
  const now = opts.now || (() => Date.now())
  const intervalMs = opts.intervalMs ?? WORKBENCH_SYNC_INTERVAL_MS
  const fullIntervalMs = opts.fullIntervalMs ?? WORKBENCH_FULL_RECONCILE_INTERVAL_MS
  const highlightMs = opts.highlightMs ?? NEW_ORDER_HIGHLIGHT_MS
  const maxDeltaPages = opts.maxDeltaPages ?? WORKBENCH_DELTA_MAX_PAGES
  const deltaFailFallback = opts.deltaFailFallback ?? WORKBENCH_DELTA_FAIL_FALLBACK
  const onChange = opts.onChange || (() => {})
  const setTimeoutFn = opts.setTimeoutFn || ((fn, ms) => setTimeout(fn, ms))
  const clearTimeoutFn = opts.clearTimeoutFn || ((id) => clearTimeout(id))

  let orders = []
  let knownPendingIds = new Set()
  let hasBaseline = false
  let cursor = null
  let lastFullAt = null
  let initialLoading = false
  let backgroundSyncing = false
  let inFlight = false
  let fullSyncPending = false
  let consecutiveDeltaFailures = 0
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
  let lastMode = null

  function emit() {
    onChange(getState())
  }

  function getState() {
    return {
      orders,
      knownPendingIds: new Set(knownPendingIds),
      hasBaseline,
      cursor,
      lastFullAt,
      initialLoading,
      backgroundSyncing,
      inFlight,
      fullSyncPending,
      syncFailed,
      networkOnline,
      lastSuccessfulSyncAt,
      pageVisible,
      running,
      authStopped,
      highlightIds: new Set(highlightIds),
      lastNewIds: lastNewIds.slice(),
      lastMode,
      consecutiveDeltaFailures,
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
      sync('auto')
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

  function commitOrders(list, { allowAlert }) {
    const filtered = filterOrders(Array.isArray(list) ? list : [])
    const sorted = sortOrdersFifo(filtered)
    const currentAlertIds = alertIdsFromOrders(sorted)
    let newIds = []
    if (allowAlert && alertsEnabled && hasBaseline) {
      newIds = diffNewPendingIds(knownPendingIds, currentAlertIds)
    }
    orders = sorted
    knownPendingIds = currentAlertIds
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
    return newIds
  }

  function isInvalidCursorError(err) {
    const status = err?.response?.status
    const code = err?.response?.data?.msg || err?.response?.data?.code || err?.code || err?.message
    return status === 400 && String(code || '').includes('INVALID_CURSOR')
  }

  function isAuthError(err) {
    const status = err?.response?.status
    return status === 401 || status === 403
  }

  async function runFull() {
    lastMode = 'full'
    const raw = await fetchFull()
    let list
    let nextCursor = null
    if (Array.isArray(raw)) {
      list = raw
    } else if (raw && typeof raw === 'object') {
      list = Array.isArray(raw.orders) ? raw.orders : []
      nextCursor = raw.cursor != null ? String(raw.cursor) : null
    } else {
      list = []
    }
    const newIds = commitOrders(list, { allowAlert: true })
    if (nextCursor) cursor = nextCursor
    lastFullAt = now()
    consecutiveDeltaFailures = 0
    fullSyncPending = false
    emit()
    return { ok: true, mode: 'full', newIds, orders }
  }

  async function runDelta() {
    lastMode = 'delta'
    if (!cursor) {
      return runFull()
    }
    let pages = 0
    let workingCursor = cursor
    let workingOrders = orders
    while (pages < maxDeltaPages) {
      pages += 1
      const page = await fetchChanges(workingCursor)
      const items = Array.isArray(page?.items) ? page.items : []
      const removed = Array.isArray(page?.removed_ids) ? page.removed_ids : []
      const next = page?.next_cursor != null ? String(page.next_cursor) : workingCursor
      workingOrders = applyWorkbenchDelta(workingOrders, items, removed, filterOrders)
      workingCursor = next
      if (!page?.has_more) break
      if (pages >= maxDeltaPages && page?.has_more) {
        // Drain safety: fall back to full rather than skip remaining pages.
        cursor = workingCursor
        return runFull()
      }
    }
    cursor = workingCursor
    const newIds = commitOrders(workingOrders, { allowAlert: true })
    // commitOrders re-filters; keep FIFO from apply
    orders = sortOrdersFifo(filterOrders(workingOrders))
    consecutiveDeltaFailures = 0
    emit()
    return { ok: true, mode: 'delta', newIds, orders }
  }

  function shouldFull(mode) {
    if (mode === 'full') return true
    if (mode === 'delta') return false
    if (!useDelta) return true
    if (!hasBaseline || !cursor) return true
    if (consecutiveDeltaFailures >= deltaFailFallback) return true
    if (lastFullAt == null) return true
    if (now() - lastFullAt >= fullIntervalMs) return true
    return false
  }

  async function sync(mode = 'auto') {
    if (!running || authStopped) return { skipped: true, reason: 'stopped' }
    if (inFlight) {
      if (mode === 'full' || shouldFull(mode)) fullSyncPending = true
      return { skipped: true, reason: 'in_flight' }
    }

    const wantFull = shouldFull(mode)
    inFlight = true
    if (!hasBaseline) initialLoading = true
    else backgroundSyncing = true
    emit()

    try {
      if (wantFull) {
        return await runFull()
      }
      try {
        return await runDelta()
      } catch (err) {
        if (isAuthError(err)) throw err
        if (isInvalidCursorError(err)) {
          cursor = null
          consecutiveDeltaFailures = 0
          return await runFull()
        }
        consecutiveDeltaFailures += 1
        if (consecutiveDeltaFailures >= deltaFailFallback) {
          return await runFull()
        }
        throw err
      }
    } catch (err) {
      if (isAuthError(err)) {
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
      if (fullSyncPending && running && !authStopped) {
        fullSyncPending = false
        // Priority full after in-flight delta/full finishes.
        Promise.resolve()
          .then(() => sync('full'))
          .catch(() => {})
      } else {
        scheduleNext()
      }
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
      sync('full')
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
      sync('full')
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
    sync('full')
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
    syncNow: () => sync('full'),
    syncDelta: () => sync('delta'),
    setVisible,
    setOnline,
    getState,
    isHighlighted,
    pendingIdsFromOrders,
    diffNewPendingIds,
  }
}
