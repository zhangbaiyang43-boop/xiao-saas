// 轻量错误上报。之前很多 catch(e){} 是彻底吞掉的，线上出了问题只能等顾客
// 投诉、翻服务端日志去猜。这里不追求接一套正式 APM（成本高、还要后端配合建
// 看板），先把"至少能看见"这一步补上：本地滚动存最近若干条（跟 utils/perf.js
// 的 P50/P95 采样是同一个思路，同一套"本地兜底、以后再考虑上报聚合"的哲学），
// 有原生上报能力（微信小程序的 wx.reportMonitor）时顺手也报一份，没有该能力
// 的平台（H5、或者还没在小程序后台登记这个监控项）就跳过，绝不影响主流程。
const STORAGE_KEY = 'error_reports'
const MAX_REPORTS = 30

function readReports() {
  try {
    const raw = uni.getStorageSync(STORAGE_KEY)
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

function writeReports(reports) {
  try { uni.setStorageSync(STORAGE_KEY, reports) } catch { /* 存储写满之类的边界情况直接放弃，不影响正常点餐 */ }
}

// scene 是"这次失败发生在哪个业务动作里"的简短标识（比如
// 'checkout.submit_order'、'dining.bind_participant'），不是错误消息本身——
// 错误消息千变万化没法用来分类，scene 才是以后能在后台按事发场景聚合统计的
// 维度。extra 放不敏感的排查上下文（订单号、桌号之类），别塞用户隐私信息。
export function reportError(scene, err, extra) {
  const message = err?.message || err?.errMsg || String(err || '')
  const entry = { t: Date.now(), scene, message: String(message).slice(0, 200), extra: extra || undefined }

  console.error(`[error] ${scene}:`, message, extra || '')

  try {
    const reports = readReports()
    reports.push(entry)
    if (reports.length > MAX_REPORTS) reports.splice(0, reports.length - MAX_REPORTS)
    writeReports(reports)
  } catch { /* 本地兜底失败就算了，不能因为记录错误本身又抛出一个错误 */ }

  try {
    // wx.reportMonitor 的监控项名字需要先在小程序管理后台"运维中心 > 性能监控"
    // 里登记成"自定义监控指标"才会真的被采集，这里按 scene 直接报，接的时候
    // 在后台把用到的 scene 名注册一遍即可，代码这边不用再改。
    if (typeof wx !== 'undefined' && typeof wx.reportMonitor === 'function') {
      wx.reportMonitor(scene, 1)
    }
  } catch { /* 上报通道本身出问题，静默放弃，不能反过来影响业务流程 */ }
}

export function getRecentErrors() {
  return readReports()
}

export function clearErrors() {
  // 清不掉本地错误采样列表不影响任何真实业务，刻意留空。
  // eslint-disable-next-line no-empty
  try { uni.removeStorageSync(STORAGE_KEY) } catch {}
}
