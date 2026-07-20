export const isValidPhone = (value) => {
  if (!value) return true
  return /^1\d{10}$/.test(value)
}

export const phoneError = (value) => {
  if (!isValidPhone(value)) return '手机号格式不正确'
  return ''
}

export const requiredError = (value, label) => {
  if (value === undefined || value === null || value === '') return `请填写${label}`
  if (Array.isArray(value) && !value.length) return `请选择${label}`
  return ''
}

export const positiveNumberError = (value, label) => {
  if (Number(value || 0) <= 0) return `${label}必须大于 0`
  return ''
}

export const firstError = (...errors) => errors.find(Boolean) || ''
