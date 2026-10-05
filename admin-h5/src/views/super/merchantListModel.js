// Pure display / filter logic for the Super Admin merchant list (Phase 04).
//
// No Vue, no network. Everything here only reads fields the existing
// GET /api/super/merchants read model already returns; it never invents a status.
// The label helpers below were moved out of SuperAdmin.vue unchanged so the list and
// the merchant detail page keep a single source of truth.
import { formatBeijingDate } from '../../utils/beijingTime'

export const ACCOUNT_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'enabled', label: '启用' },
  { value: 'disabled', label: '已停用' },
]

export const PAYMENT_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'unconfigured', label: '未配置' },
  { value: 'pending', label: '待验证' },
  { value: 'verified', label: '已验证' },
  { value: 'paused', label: '暂停' },
]

export const PLAN_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'trial', label: '试用中' },
  { value: 'active', label: '付费中' },
  { value: 'free', label: '免费版' },
  { value: 'ended', label: '已到期' },
]

// One-direction sorts only: soonest expiry first, busiest today first.
export const SORT_OPTIONS = ['expiry', 'orders']

export const QUERY_KEYS = ['q', 'account', 'payment', 'plan', 'sort']

export function statusText(status) {
  return { unconfigured: '未配置', pending: '待验证', verified: '已验证', paused: '暂停' }[status] || '未配置'
}

export function statusClass(status) {
  return { unconfigured: 'pay-off', pending: 'pay-pending', verified: 'pay-on', paused: 'pay-paused' }[status] || 'pay-off'
}

export function maskPhone(value) {
  const v = (value || '').trim()
  if (v.length !== 11) return v || '-'
  return `${v.slice(0, 3)}****${v.slice(-4)}`
}

export function matchesPlanFilter(sub, filter) {
  if (!sub || sub.load_error) return false
  if (filter === 'trial') return !!sub.is_trial || sub.status === 'TRIAL'
  if (filter === 'active') return sub.status === 'ACTIVE'
  if (filter === 'free') return sub.status === 'FREE'
  if (filter === 'ended') return sub.status === 'EXPIRED' || sub.status === 'CANCELLED'
  return true
}

export function subscriptionLabel(sub) {
  if (!sub || sub.load_error) return '套餐加载失败'
  const name = sub.plan_name || '免费版'
  if (sub.is_trial || sub.status === 'TRIAL') return `${name}试用`
  if (sub.status === 'ACTIVE' || sub.status === 'FREE') return name
  if (sub.status === 'EXPIRED') return '已到期'
  if (sub.status === 'CANCELLED') return '已取消'
  return name
}

export function expiryLabel(sub) {
  if (!sub || sub.load_error || !sub.expires_at) return '—'
  const date = formatBeijingDate(sub.expires_at)
  if (!date) return '—'
  if (typeof sub.days_remaining === 'number') return `${date} · 剩余 ${sub.days_remaining} 天`
  return date
}

export function channelLabel(channel) {
  if (!channel || channel.load_error) return '加载失败'
  if (!channel.bound) return '未绑定'
  return channel.partner_name || '渠道伙伴资料缺失'
}

// ---- list-only cells (two lines per cell, built from the same fields as the labels above) ----

// { name, tag } where tag is '' | '试用' | '已到期' | '已取消'; name is the plan the read model reports.
export function planCell(sub) {
  if (!sub || sub.load_error) return { name: '套餐加载失败', tag: '', error: true }
  const name = sub.plan_name || '免费版'
  if (sub.is_trial || sub.status === 'TRIAL') return { name, tag: '试用', error: false }
  if (sub.status === 'EXPIRED') return { name, tag: '已到期', error: false }
  if (sub.status === 'CANCELLED') return { name, tag: '已取消', error: false }
  return { name, tag: '', error: false }
}

// { date, remaining, urgent }: date is '—' when the read model has none; remaining is '' or '剩余 N 天'.
// urgent is presentation only (<= 7 days left); it does not create a new subscription state.
export function expiryCell(sub) {
  if (!sub || sub.load_error || !sub.expires_at) return { date: '—', remaining: '', urgent: false }
  const date = formatBeijingDate(sub.expires_at) || '—'
  if (typeof sub.days_remaining !== 'number') return { date, remaining: '', urgent: false }
  return { date, remaining: `剩余 ${sub.days_remaining} 天`, urgent: sub.days_remaining <= 7 }
}

export function accountText(merchant) {
  return merchant.status ? '启用' : '已停用'
}

export function todayOrdersText(merchant) {
  const n = merchant.today_orders
  return typeof n === 'number' ? String(n) : '—'
}

// ---- filter state <-> URL query ------------------------------------------------------------

function allowed(options, value) {
  return options.some(option => option.value === value) ? value : ''
}

// Unknown or missing query values fall back to "no filter"; nothing outside the lists is trusted.
export function filtersFromQuery(query = {}) {
  const pick = key => {
    const raw = Array.isArray(query[key]) ? query[key][0] : query[key]
    return raw == null ? '' : String(raw)
  }
  return {
    q: pick('q').trim(),
    account: allowed(ACCOUNT_OPTIONS, pick('account')),
    payment: allowed(PAYMENT_OPTIONS, pick('payment')),
    plan: allowed(PLAN_OPTIONS, pick('plan')),
    sort: SORT_OPTIONS.includes(pick('sort')) ? pick('sort') : '',
  }
}

// Merge a patch into the current query: keeps unrelated keys, drops empty values.
export function queryWithPatch(currentQuery, patch) {
  const next = { ...currentQuery }
  for (const key of Object.keys(patch)) {
    const value = patch[key]
    if (value === '' || value == null) delete next[key]
    else next[key] = value
  }
  return next
}

export function hasActiveFilter(filters) {
  return !!(filters.q || filters.account || filters.payment || filters.plan)
}

// ---- filtering and sorting (client side; the API returns the full list) -------------------

export function filterMerchants(merchants, filters) {
  const q = (filters.q || '').trim()
  const qLower = q.toLowerCase()
  return merchants.filter(m => {
    if (filters.account === 'enabled' && !m.status) return false
    if (filters.account === 'disabled' && m.status) return false
    if (filters.payment && (m.payment_status || 'unconfigured') !== filters.payment) return false
    if (filters.plan && !matchesPlanFilter(m.subscription, filters.plan)) return false
    if (!q) return true
    const tenantId = String(m.tenant_id || '').toLowerCase()
    return String(m.name || '').includes(q) || (m.phone || '').includes(q) || tenantId.includes(qLower)
  })
}

function expiryTime(m) {
  const sub = m.subscription
  if (!sub || sub.load_error || !sub.expires_at) return Number.POSITIVE_INFINITY
  const t = Date.parse(sub.expires_at)
  return Number.isNaN(t) ? Number.POSITIVE_INFINITY : t
}

export function sortMerchants(merchants, sort) {
  if (!SORT_OPTIONS.includes(sort)) return merchants
  const indexed = merchants.map((m, i) => ({ m, i }))
  if (sort === 'expiry') {
    indexed.sort((a, b) => (expiryTime(a.m) - expiryTime(b.m)) || (a.i - b.i))
  } else {
    const orders = m => (typeof m.today_orders === 'number' ? m.today_orders : -1)
    indexed.sort((a, b) => (orders(b.m) - orders(a.m)) || (a.i - b.i))
  }
  return indexed.map(item => item.m)
}
