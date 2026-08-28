const FALLBACK_ERROR_MESSAGE = '桌贴生成失败，请稍后重试'

export const classifyTableStickerCode = (code) => {
  if (code?.channel !== 'TABLE' || code?.entry_type !== 'table') return { valid: false, reason: '不是桌贴码' }
  if (Number(code?.status) !== 1) return { valid: false, reason: '桌码已停用' }
  if (code?.env_version !== 'release') return { valid: false, reason: '体验码，请先重新生成正式码' }
  if (code?.generation_status !== 'SUCCESS' || !String(code?.image_url || '').trim()) {
    return { valid: false, reason: '桌码图片不可用' }
  }
  if (!String(code?.table_no || '').trim()) return { valid: false, reason: '缺少桌号' }
  return { valid: true, reason: '' }
}

export const selectedExportableCodes = (codes, selectedIds) => {
  const normalizedIds = new Set(Array.from(selectedIds || [], value => String(value)))
  return (codes || []).filter(code => (
    normalizedIds.has(String(code?.id)) && classifyTableStickerCode(code).valid
  ))
}

export const parseBlobErrorMessage = async (blob) => {
  try {
    const data = JSON.parse(await blob.text())
    return data?.msg || data?.message || FALLBACK_ERROR_MESSAGE
  } catch {
    return FALLBACK_ERROR_MESSAGE
  }
}

export const triggerBlobDownload = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  let anchor
  try {
    anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
  } finally {
    try {
      anchor?.remove()
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 0)
    }
  }
}
