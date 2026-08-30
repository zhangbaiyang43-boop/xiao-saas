// 时间一律按北京时间口径，且先补 Z 再解析（后端存 naive UTC，无时区后缀）。
// 见 utils/beijingTime.js 的说明。
import {
  formatBeijingDate,
  formatBeijingDateTime,
  isBeijingThisMonth,
  isBeijingToday,
} from './beijingTime.js'

export const unwrapList = (res) => {
  if (Array.isArray(res?.data)) return res.data
  if (Array.isArray(res?.data?.items)) return res.data.items
  return []
}

export const unwrapPage = (res) => {
  const data = res?.data || {}
  if (Array.isArray(data)) {
    return {
      items: data,
      total: data.length,
      page: 1,
      pageSize: data.length || 20
    }
  }
  return {
    items: Array.isArray(data.items) ? data.items : [],
    total: Number(data.total || 0),
    page: Number(data.page || 1),
    pageSize: Number(data.page_size || data.limit || 20)
  }
}

export const toPageParams = ({ page = 1, pageSize = 20 } = {}) => {
  const safePage = Math.max(Number(page || 1), 1)
  const safePageSize = Math.max(Number(pageSize || 20), 1)
  return {
    skip: (safePage - 1) * safePageSize,
    limit: safePageSize
  }
}

export const formatMoney = (value) => {
  const amount = Number(value || 0)
  return amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

export const formatDateTime = (value) => formatBeijingDateTime(value) || '-'

export const formatDate = (value) => formatBeijingDate(value) || '-'

export const isThisMonth = (value) => isBeijingThisMonth(value)

export const isToday = (value) => isBeijingToday(value)
