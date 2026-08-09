export function formatMoney(cents = 0) {
  const value = Number(cents || 0)
  const sign = value < 0 ? '-' : ''
  return `${sign}¥${(Math.abs(value) / 100).toFixed(2)}`
}

export function merchantNetEarnedText(cents = 0) {
  const value = Number(cents || 0)
  if (value > 0) return `已产生收益 ${formatMoney(value)}`
  if (value < 0) return `当前净收益 ${formatMoney(value)}`
  return '暂未产生收益'
}
