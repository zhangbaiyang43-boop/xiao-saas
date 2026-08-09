const activePollers = new Set()

export function stopActivePollers() {
  activePollers.forEach((poller) => poller.stop())
  activePollers.clear()
}

function newestId(items = []) {
  return items.reduce((max, item) => Math.max(max, Number(item?.id || 0)), 0)
}

export function createDashboardPoller({
  intervalMs = 30000,
  fetchDashboard,
  onData,
  onNewEarn,
  onError,
}) {
  let stopped = false
  let timer = null
  let inFlight = false
  let initialized = false
  let cursor = 0

  async function run() {
    if (stopped || inFlight) return
    if (typeof document !== 'undefined' && document.hidden) return schedule()
    inFlight = true
    try {
      const data = await fetchDashboard()
      const latest = Array.isArray(data?.latest_commissions) ? data.latest_commissions : []
      const nextCursor = newestId(latest)
      if (initialized && nextCursor > cursor) {
        const fresh = latest
          .filter((item) => Number(item.id || 0) > cursor && item.entry_type === 'EARN')
          .sort((a, b) => Number(a.id) - Number(b.id))
        fresh.forEach((item) => onNewEarn?.(item))
      }
      cursor = Math.max(cursor, nextCursor)
      initialized = true
      onData?.(data)
    } catch (error) {
      onError?.(error)
    } finally {
      inFlight = false
      schedule()
    }
  }

  function schedule() {
    if (stopped) return
    clearTimeout(timer)
    timer = setTimeout(run, intervalMs)
  }

  function start() {
    stopped = false
    activePollers.add(api)
    run()
  }

  function stop() {
    stopped = true
    clearTimeout(timer)
    activePollers.delete(api)
  }

  function refreshNow() {
    return run()
  }

  function setVisible() {
    if (!stopped && typeof document !== 'undefined' && !document.hidden) run()
  }

  const api = { start, stop, refreshNow, setVisible }
  return api
}
