export function appendPageItems(current = [], next = []) {
  const seen = new Set()
  const result = []
  for (const item of [...current, ...next]) {
    const key = String(item?.id ?? '')
    if (!key || seen.has(key)) continue
    seen.add(key)
    result.push(item)
  }
  return result
}
