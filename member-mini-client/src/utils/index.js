export const formatDate = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export const formatDateTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return `${formatDate(value)} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

export const formatMoney = (value) => {
  const num = Number(value || 0)
  return Number.isInteger(num) ? String(num) : num.toFixed(2)
}

export const formatPhone = (phone) => {
  if (!phone) return '-'
  const value = String(phone)
  if (value.length === 11) return value.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')
  return value
}

export const couponStatusText = (status) => {
  const map = {
    UNUSED: '可使用',
    USED: '已使用',
    EXPIRED: '已过期',
    REVOKED: '已收回'
  }
  return map[status] || status || '-'
}
