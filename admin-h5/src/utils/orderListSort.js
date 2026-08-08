/**
 * 商家工作台订单列表排序（OrderManage.vue Source of Truth）。
 * 后端 list_orders 按 created_at DESC 返回；此处有意二次排序：
 * - 履约态 FIFO（createdAt ASC）
 * - 终态/查看态最新优先（createdAt DESC）
 */

const STATUS_PRIORITY = {
  pending: 0,
  preparing: 1,
  done: 2,
  settled: 3,
  rejected: 4,
  cancelled: 5,
  pending_payment: 6,
}

/** 厨房/履约队列：等待越久越靠前 */
const ACTIVE_ASC_STATUSES = new Set(['pending', 'preparing', 'done'])

export function parseOrderTime(value) {
  if (value == null || value === '') return 0
  const t = new Date(value).getTime()
  return Number.isFinite(t) ? t : 0
}

function compareIdAsc(a, b) {
  const sa = String(a?.id ?? '')
  const sb = String(b?.id ?? '')
  try {
    const ba = BigInt(sa)
    const bb = BigInt(sb)
    if (ba < bb) return -1
    if (ba > bb) return 1
    return 0
  } catch {
    if (sa < sb) return -1
    if (sa > sb) return 1
    return 0
  }
}

function compareIdDesc(a, b) {
  return -compareIdAsc(a, b)
}

/** 同状态内时间方向（含 id 次键） */
export function compareOrderTime(a, b) {
  const aTime = parseOrderTime(a?.createdAt)
  const bTime = parseOrderTime(b?.createdAt)
  if (ACTIVE_ASC_STATUSES.has(a?.status)) {
    return aTime - bTime || compareIdAsc(a, b)
  }
  return bTime - aTime || compareIdDesc(a, b)
}

export function compareMerchantOrders(a, b) {
  const pa = STATUS_PRIORITY[a?.status] ?? 9
  const pb = STATUS_PRIORITY[b?.status] ?? 9
  if (pa !== pb) return pa - pb
  return compareOrderTime(a, b)
}

export function sortMerchantOrders(list) {
  return [...(Array.isArray(list) ? list : [])].sort(compareMerchantOrders)
}
