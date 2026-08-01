export const routeByScanResult = (res = {}) => {
  const path = res.path || ''
  if (path) {
    const target = path.startsWith('/') ? path : `/${path}`
    uni.navigateTo({ url: target })
    return
  }

  const result = res.result || ''
  const sceneMatch = result.match(/[?&]scene=([^&]+)/)
  const scene = sceneMatch ? decodeURIComponent(sceneMatch[1]).trim() : result.trim()
  if (!scene) {
    uni.showToast({ title: '没有识别到桌贴码', icon: 'none' })
    return
  }
  uni.setStorageSync('entrance_scene', scene)
  uni.navigateTo({ url: `/pages/entry/index?scene=${encodeURIComponent(scene)}` })
}

export const scanStoreCode = () => {
  uni.scanCode({
    onlyFromCamera: true,
    success: routeByScanResult,
    fail: () => {
      uni.showToast({ title: '请扫描桌贴点餐码', icon: 'none' })
    }
  })
}
