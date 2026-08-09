import { formatMoney } from './money.js'

export const leadStatusText = (status) => ({
  PROTECTED: '已报备',
  CONTACTED: '跟进中',
  DEMO: '已演示',
  WON: '已成交',
  LOST: '已失效',
  EXPIRED: '已失效',
}[status] || '处理中')

export const ledgerStatusText = (status) => ({
  PENDING: '待结算',
  AVAILABLE: '可结算',
  SETTLED: '已结算',
  REVERSED: '已生效',
}[status] || '已生效')

export const entryTypeText = (type) => ({
  EARN: '软件服务费',
  REVERSAL: '退款调整',
  ADJUSTMENT: '收益调整',
}[type] || '收益')

export const partnerStatusText = (status) => ({
  ACTIVE: '合作中',
  SUSPENDED: '暂停新增',
  DISABLED: '已停用',
}[status] || '合作中')

export const partnerTypeText = (type) => ({
  INDIVIDUAL: '个人渠道',
  COMPANY: '企业渠道',
  AGENCY: '服务商渠道',
}[type] || '')

export const bindingStatusText = (status) => ({
  ACTIVE: '合作中',
  SUSPENDED: '暂停新增',
  DISABLED: '已停用',
}[status] || '合作中')

export function signedLedgerAmount(item) {
  const raw = Number(item?.commission_amount_cents || 0)
  const amount = item?.entry_type === 'REVERSAL' ? -Math.abs(raw) : Math.abs(raw)
  return amount >= 0 ? `+${formatMoney(amount)}` : formatMoney(amount)
}
