export function parseDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function pad(value) {
  return String(value).padStart(2, '0')
}

export function formatDate(value) {
  const date = parseDate(value)
  if (!date) return ''
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function formatDateTime(value) {
  const date = parseDate(value)
  if (!date) return ''
  return `${formatDate(value)} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatShortDate(value) {
  const date = parseDate(value)
  if (!date) return ''
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatMonthDay(value) {
  const date = parseDate(value)
  if (!date) return ''
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function formatRelativeTime(value) {
  const date = parseDate(value)
  if (!date) return ''
  const diff = Date.now() - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`
  return formatShortDate(value)
}
