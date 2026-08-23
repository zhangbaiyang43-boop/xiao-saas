/** Canonical order status display copy. Prefer API status_text; never render the raw token. */
export const ORDER_STATUS_TEXT = {
  pending_payment: '待支付',
  pending: '待接单',
  preparing: '制作中',
  done: '已上餐',
  settled: '已结账',
  cancelled: '已取消',
  rejected: '已拒单',
}

export const UNKNOWN_ORDER_STATUS_TEXT = '处理中'

const LATIN_TOKEN = /^[A-Za-z][A-Za-z0-9_]*$/

export function formatOrderStatusText(status, statusText) {
  const fromApi = typeof statusText === 'string' ? statusText.trim() : ''
  if (fromApi && !LATIN_TOKEN.test(fromApi)) return fromApi
  const mapped = ORDER_STATUS_TEXT[String(status || '')]
  if (mapped) return mapped
  return UNKNOWN_ORDER_STATUS_TEXT
}
