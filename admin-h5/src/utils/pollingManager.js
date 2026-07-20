const DEFAULT_INTERVAL = 30000
const HDEN_INTERVAL = 120000
const LE_INTERVAL = 90000
const LE_AFTER = 5 * 60 * 1000
const JITTER_RATIO = 0.1

const tasks = new Map()
let idle = false
let lastActiveAt = Date.now()
let listenersReady = false
let idleTimer = null

function now() {
  return Date.now()
}

function isVisible() {
  return typeof document === 'undefined' || document.visibilityState === 'visible'
}

function withJitter(ms) {
  const value = Number(ms || DEFAULT_INTERVAL)
  const offset = value * JITTER_RATIO * (Math.random() * 2 - 1)
  return Math.max(1000, Math.round(value + offset))
}

function resolveInterval(task) {
  if (!isVisible()) return task.hiddenInterval ?? HDEN_INTERVAL
  if (idle) return task.idleInterval ?? LE_INTERVAL
  return typeof task.interval === 'function' ? task.interval() : (task.interval ?? DEFAULT_INTERVAL)
}

function clearTaskTimer(task) {
  if (task.timer) {
    clearTimeout(task.timer)
    task.timer = null
  }
}

function schedule(task, delay) {
  clearTaskTimer(task)
  if (!task.active || task.paused) return
  task.timer = setTimeout(() => runTask(task), withJitter(delay ?? resolveInterval(task)))
}

async function runTask(task, forced = false) {
  if (!task.active || task.paused) return
  if (task.running) {
    task.skipped += 1
    if (import.meta.env.DEV) {
      console.info('[polling] skipped running task', { key: task.key, skipped: task.skipped })
    }
    schedule(task)
    return
  }

  task.running = true
  task.lastRunAt = now()
  try {
    await task.task({ key: task.key, fromPolling: !forced, forced })
    task.failCount = 0
  } catch (error) {
    task.failCount += 1
    if (import.meta.env.DEV) {
      console.warn('[polling] task failed', { key: task.key, failCount: task.failCount, error })
    }
  } finally {
    task.running = false
    if (!task.active || task.paused) return
    if (task.failCount >= 3) schedule(task, 120000)
    else if (task.failCount >= 1) schedule(task, 30000)
    else schedule(task)
  }
}

function markActive() {
  const wasIdle = idle
  lastActiveAt = now()
  idle = false
  if (wasIdle) {
    tasks.forEach((task) => {
      if (task.active && !task.paused && task.refreshOnActive !== false) {
        runTask(task, true)
      } else {
        schedule(task)
      }
    })
  }
}

function checkIdle() {
  const nextIdle = now() - lastActiveAt >= LE_AFTER
  if (nextIdle !== idle) {
    idle = nextIdle
    tasks.forEach((task) => schedule(task))
  }
}

function onVisibilityChange() {
  tasks.forEach((task) => {
    if (!task.active || task.paused) return
    if (isVisible() && task.refreshOnVisible !== false) {
      runTask(task, true)
    } else {
      schedule(task)
    }
  })
}

function ensureListeners() {
  if (listenersReady || typeof window === 'undefined') return
  listenersReady = true
  const activeEvents = ['mousemove', 'keydown', 'click', 'touchstart']
  activeEvents.forEach((eventName) => window.addEventListener(eventName, markActive, { passive: true }))
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }
  idleTimer = setInterval(checkIdle, 30000)
}

export function startPolling(key, options) {
  ensureListeners()
  if (!key || typeof options?.task !== 'function') {
    throw new Error('polling key and task are required')
  }

  const existing = tasks.get(key)
  if (existing) {
    existing.active = true
    existing.paused = false
    existing.task = options.task
    existing.interval = options.interval ?? existing.interval
    existing.hiddenInterval = options.hiddenInterval ?? existing.hiddenInterval
    existing.idleInterval = options.idleInterval ?? existing.idleInterval
    existing.refreshOnVisible = options.refreshOnVisible ?? existing.refreshOnVisible
    existing.refreshOnActive = options.refreshOnActive ?? existing.refreshOnActive
    if (options.immediate !== false) runTask(existing, true)
    else schedule(existing)
    return () => stopPolling(key)
  }

  const task = {
    key,
    task: options.task,
    interval: options.interval ?? DEFAULT_INTERVAL,
    hiddenInterval: options.hiddenInterval ?? HDEN_INTERVAL,
    idleInterval: options.idleInterval ?? LE_INTERVAL,
    refreshOnVisible: options.refreshOnVisible,
    refreshOnActive: options.refreshOnActive,
    active: true,
    paused: false,
    running: false,
    timer: null,
    failCount: 0,
    skipped: 0,
    lastRunAt: 0,
  }
  tasks.set(key, task)
  if (options.immediate !== false) runTask(task, true)
  else schedule(task)
  return () => stopPolling(key)
}

export function stopPolling(key) {
  const task = tasks.get(key)
  if (!task) return
  task.active = false
  clearTaskTimer(task)
  tasks.delete(key)
}

export function pausePolling(key) {
  const task = tasks.get(key)
  if (!task) return
  task.paused = true
  clearTaskTimer(task)
}

export function resumePolling(key, immediate = true) {
  const task = tasks.get(key)
  if (!task) return
  task.paused = false
  if (immediate) runTask(task, true)
  else schedule(task)
}

export function stopAllPolling() {
  tasks.forEach((task) => {
    task.active = false
    clearTaskTimer(task)
  })
  tasks.clear()
}

export function getPollingState() {
  return {
    visible: isVisible(),
    idle,
    size: tasks.size,
    tasks: Array.from(tasks.values()).map((task) => ({
      key: task.key,
      running: task.running,
      failCount: task.failCount,
      skipped: task.skipped,
      lastRunAt: task.lastRunAt,
    })),
  }
}

export default {
  start: startPolling,
  stop: stopPolling,
  pause: pausePolling,
  resume: resumePolling,
  stopAll: stopAllPolling,
  state: getPollingState,
}
