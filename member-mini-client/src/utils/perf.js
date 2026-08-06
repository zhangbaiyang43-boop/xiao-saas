// 第0批性能埋点：本地滚动窗口存样本，算 P50/P95，不依赖后端新增接口。
// 目的是给后续每一项"进页/结算"优化提供一把能验证效果的尺子，不是长期的生产监控方案——
// 真要看全量用户的分布，以后再考虑上报到后端聚合。

const STORAGE_PREFIX = 'perf_samples_'
const START_MARK_PREFIX = 'perf_start_'
const MAX_SAMPLES = 60 // 每个指标只留最近 60 条，够算 P50/P95，又不会把本地存储撑爆

function readSamples(metric) {
  try {
    const raw = uni.getStorageSync(STORAGE_PREFIX + metric)
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

function writeSamples(metric, samples) {
  try {
    uni.setStorageSync(STORAGE_PREFIX + metric, samples)
  } catch { /* 存储写满之类的边界情况直接放弃这次埋点，不影响正常点餐 */ }
}

// durationMs 是这次测到的耗时；meta 是任意补充信息（比如接口 URL、服务端 X-Process-Time-Ms），
// 只用来排查问题，不参与 P50/P95 计算。
export function recordSample(metric, durationMs, meta) {
  if (!metric || !(durationMs >= 0)) return
  const samples = readSamples(metric)
  samples.push({ t: Date.now(), ms: Math.round(durationMs), meta: meta || undefined })
  if (samples.length > MAX_SAMPLES) samples.splice(0, samples.length - MAX_SAMPLES)
  writeSamples(metric, samples)
  console.log(`[perf] ${metric}: ${Math.round(durationMs)}ms`, meta || '')
}

function percentile(sortedMs, p) {
  if (!sortedMs.length) return 0
  const idx = Math.min(sortedMs.length - 1, Math.ceil((p / 100) * sortedMs.length) - 1)
  return sortedMs[Math.max(0, idx)]
}

export function getStats(metric) {
  const samples = readSamples(metric)
  const sorted = samples.map((s) => s.ms).sort((a, b) => a - b)
  if (!sorted.length) return { metric, count: 0, avg: 0, p50: 0, p95: 0, min: 0, max: 0 }
  const sum = sorted.reduce((a, b) => a + b, 0)
  return {
    metric,
    count: sorted.length,
    avg: Math.round(sum / sorted.length),
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    min: sorted[0],
    max: sorted[sorted.length - 1],
  }
}

// stage_* 三个是把 scan_to_interactive 这一个总耗时拆开看的分段埋点（第 0 批只有
// 一个总数，看不出 6-7 秒到底花在冷启动、等接口、还是渲染上，没法对症下药）：
// - stage_cold_start_to_onload：小程序冷启动（含包下载/注入/路由）到 menu.vue
//   的 onLoad 真正跑起来，这段完全在小程序框架和网络里，业务代码基本管不到。
// - stage_onload_to_menu_ready：onLoad 跑起来到店铺设置+菜单数据都拿到，
//   这段是接口耗时，慢的话应该去查请求本身或者要不要加缓存。
// - stage_menu_ready_to_render：数据到手到页面真正渲染出来（nextTick 之后），
//   这段慢大多是数据量或渲染本身的问题。
// 三段加起来约等于 scan_to_interactive（后者继续保留，图的是能跟第 0 批的历史
// 数据直接对比，不因为拆分就断了趋势线）。
const TRACKED_METRICS = [
  'scan_to_interactive',
  'stage_cold_start_to_onload',
  'stage_onload_to_menu_ready',
  'stage_menu_ready_to_render',
  'menu_api',
  'cart_open',
  'submit_order',
]

export function getAllStats() {
  return TRACKED_METRICS.map(getStats)
}

export function clearAll() {
  TRACKED_METRICS.forEach((metric) => {
    // 这是纯本地的性能自测采样，清不掉顶多下次自测面板看到的还是旧数据，
    // 不影响任何真实业务，够不上上报错误的门槛，刻意留空。
    // eslint-disable-next-line no-empty
    try { uni.removeStorageSync(STORAGE_PREFIX + metric) } catch {}
  })
}

// 跨页面计时（扫码入口 App.onLaunch 到 menu.vue 首屏可交互，中间会经过一次 redirectTo，
// 页面 JS 上下文会换掉，普通的内存变量存不住，只能落本地存储）。consumeStart 读到即删，
// 避免同一个起点被后面的非扫码场景（比如页面内其它跳转）重复消费。
export function markStart(name) {
  // 同上：记不下这个起点时间戳，最多这一次的性能采样缺一条，不影响点餐主流程。
  // eslint-disable-next-line no-empty
  try { uni.setStorageSync(START_MARK_PREFIX + name, Date.now()) } catch {}
}

export function consumeStart(name) {
  try {
    const startedAt = uni.getStorageSync(START_MARK_PREFIX + name)
    uni.removeStorageSync(START_MARK_PREFIX + name)
    return typeof startedAt === 'number' && startedAt > 0 ? startedAt : null
  } catch {
    return null
  }
}
