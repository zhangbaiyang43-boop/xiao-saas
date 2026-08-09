export function sanitizeSelfParams(params = {}) {
  const clean = { ...params }
  delete clean.partner_id
  return clean
}
