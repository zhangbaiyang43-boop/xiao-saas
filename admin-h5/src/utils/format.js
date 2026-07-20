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

export const formatDateTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

export const formatDate = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('zh-CN')
}

export const isThisMonth = (value) => {
  if (!value) return false
  const date = new Date(value)
  const now = new Date()
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()
}

export const isToday = (value) => {
  if (!value) return false
  const date = new Date(value)
  const now = new Date()
  return date.toDateString() === now.toDateString()
}
