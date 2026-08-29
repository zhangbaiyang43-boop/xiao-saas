export const DEMO_SESSION_KEY = 'kaixin_demo_session'

// saas-base serializes timestamps with datetime.utcnow().isoformat() -- naive
// UTC, no timezone suffix. Date.parse() then reads a bare "YYYY-MM-DDTHH:MM:SS"
// as *local* time, so on a UTC+8 phone the 30-minute window lands 8h in the
// past and the demo shows as already expired. Append Z when no offset is present.
export function parseServerTime(value) {
  if (!value) return NaN
  const s = String(value)
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)
  return Date.parse(hasTz ? s : `${s}Z`)
}

export function saveDemoSession(storage, value) {
  storage.setItem(DEMO_SESSION_KEY, JSON.stringify(value))
}

export function readDemoSession(storage) {
  try {
    const value = JSON.parse(storage.getItem(DEMO_SESSION_KEY) || 'null')
    if (!value?.demoToken || !value?.expiresAt) return null
    const expiresAt = parseServerTime(value.expiresAt)
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
