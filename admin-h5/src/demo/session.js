export const DEMO_SESSION_KEY = 'kaixin_demo_session'

export function saveDemoSession(storage, value) {
  storage.setItem(DEMO_SESSION_KEY, JSON.stringify(value))
}

export function readDemoSession(storage) {
  try {
    const value = JSON.parse(storage.getItem(DEMO_SESSION_KEY) || 'null')
    if (!value?.demoToken || !value?.expiresAt) return null
    const expiresAt = Date.parse(value.expiresAt)
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return null
    return value
  } catch {
    return null
  }
}

export function clearDemoSession(storage) {
  storage.removeItem(DEMO_SESSION_KEY)
}

export function nextDemoAction(order) {
  if (order?.status === 'pending') {
    return { status: 'preparing', label: '接单' }
  }
  if (order?.status === 'preparing') {
    return { status: 'done', label: '制作完成' }
  }
  if (order?.status === 'done' && !order?.servedAt) {
    return { serve: true, label: '确认上菜' }
  }
  return null
}
