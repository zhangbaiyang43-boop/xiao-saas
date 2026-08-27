// 后端时间戳一律按北京时间展示。
//
// 背景（这个坑踩过一次，别再靠"看起来差不多"蒙过去）：
// saas-base 的 `created_at` 是 `Column(DateTime, default=datetime.utcnow)`——
// 存的是 **naive UTC**，`.isoformat()` 出来是 `2026-08-27T03:13:45.123456`，
// 没有 `Z`、没有 `+08:00`。
//
// JS 规范里，带时间部分但**不带时区**的字符串按「本地时间」解析。所以
// `new Date('2026-08-27T03:13:45')` 在任何设备上都被当成本地 03:13，
// 于是一笔北京时间 11:13 下的单，界面上显示成 03:13——正好差 8 小时。
//
// 两步都必须做，少一步还是错：
// 1. 补 `Z`，让它按 UTC 解析（否则起点就错了）；
// 2. 显式按 +08:00 格式化，而不是用设备本地时区（顾客可能在非中国时区，
//    但门店的营业时间、后厨的出餐时间只有一个口径——北京时间）。

const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000

// 已经带时区信息的（`Z` / `+08:00` / `-05:00`）原样交给 Date；
// 只有"裸"的日期时间串才补 Z。数字时间戳直接用。
const hasTimezone = (raw) => /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw)

export function parseServerTime(value) {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number') {
    const fromNumber = new Date(value)
    return Number.isNaN(fromNumber.getTime()) ? null : fromNumber
  }
  const raw = String(value).trim()
  if (!raw) return null
  // 只处理 ISO 风格的日期时间串；其它格式（比如已经是 '11:13' 的展示值）交回调用方。
  const isNaiveDateTime = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(raw) && !hasTimezone(raw)
  const normalized = isNaiveDateTime ? raw.replace(' ', 'T') + 'Z' : raw
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

// 把一个真实时刻挪到"北京墙上时钟"，再用 getUTC* 读出来——
// 这样不管顾客手机在哪个时区，读到的都是北京时间的年月日时分。
const beijingParts = (date) => {
  const shifted = new Date(date.getTime() + BEIJING_OFFSET_MS)
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
  }
}

const pad = (n) => String(n).padStart(2, '0')

// 'HH:mm'
export function formatBeijingTime(value) {
  const date = parseServerTime(value)
  if (!date) return ''
  const { hour, minute } = beijingParts(date)
  return pad(hour) + ':' + pad(minute)
}

// 'YYYY-MM-DD'
export function formatBeijingDate(value) {
  const date = parseServerTime(value)
  if (!date) return ''
  const { year, month, day } = beijingParts(date)
  return year + '-' + pad(month) + '-' + pad(day)
}

// 'YYYY-MM-DD HH:mm'
export function formatBeijingDateTime(value) {
  const date = parseServerTime(value)
  if (!date) return ''
  return formatBeijingDate(date) + ' ' + formatBeijingTime(date)
}

// 展示用的"人话时间"：今天只给 'HH:mm'，跨天补上「昨天」/「M月D日」。
// 一桌可能跨天（长会话、隔夜测试单），只给 'HH:mm' 会让昨晚的单看着像刚下的。
export function formatBeijingClock(value, now = new Date()) {
  const date = parseServerTime(value)
  if (!date) return ''
  const target = beijingParts(date)
  const today = beijingParts(now)
  const time = pad(target.hour) + ':' + pad(target.minute)
  if (target.year === today.year && target.month === today.month && target.day === today.day) {
    return time
  }
  const yesterday = beijingParts(new Date(now.getTime() - 24 * 60 * 60 * 1000))
  if (target.year === yesterday.year && target.month === yesterday.month && target.day === yesterday.day) {
    return '昨天 ' + time
  }
  return target.month + '月' + target.day + '日 ' + time
}
