export function buildMerchantNameMap(items = []) {
  return items.reduce((map, item) => {
    const tenantId = String(item?.tenant_id || '')
    const name = item?.merchant_display_name || item?.merchant_name || ''
    if (tenantId && name) map[tenantId] = name
    return map
  }, {})
}

export function buildMerchantNameMapFromBindings(bindings = [], leads = []) {
  const leadNames = leads.reduce((map, lead) => {
    if (lead?.id && lead?.merchant_name) map[String(lead.id)] = lead.merchant_name
    return map
  }, {})
  return bindings.reduce((map, binding) => {
    const tenantId = String(binding?.tenant_id || '')
    if (!tenantId) return map
    const leadName = leadNames[String(binding?.source_lead_id || '')]
    const bindingName = binding?.merchant_display_name || binding?.merchant_name || ''
    map[tenantId] = leadName || bindingName
    return map
  }, {})
}

export function enrichCommissions(items = [], merchantNameMap = {}) {
  return items.map((item) => {
    const tenantId = String(item?.tenant_id || '')
    const merchantName = item?.merchant_display_name || merchantNameMap[tenantId]
    return merchantName ? { ...item, merchant_display_name: merchantName } : item
  })
}
