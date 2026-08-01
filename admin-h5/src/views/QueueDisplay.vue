<template>
  <div class="display-page">
    <header class="display-header">
      <div>
        <div class="brand">饭店排位叫号</div>
        <div class="subline">请留意当前叫号，过号请联系前台</div>
      </div>
      <div class="time-block">
        <strong>{{ timeText }}</strong>
        <span>{{ dateText }}</span>
      </div>
    </header>

    <main class="hero-panel animate-in" :key="status.current_called">
      <div class="hero-label">当前叫号</div>
      <div class="current-number" :class="{ empty: !status.current_called }">
        {{ status.current_called || '暂无叫号' }}
      </div>
      <div class="next-line">下一位：{{ status.next || '暂无' }}</div>
    </main>

    <section class="count-row">
      <div class="count-item">
        <span>小桌等待</span>
        <strong>{{ status.small_count || 0 }}</strong>
      </div>
      <div class="count-item">
        <span>中桌等待</span>
        <strong>{{ status.medium_count || 0 }}</strong>
      </div>
      <div class="count-item">
        <span>大桌等待</span>
        <strong>{{ status.large_count || 0 }}</strong>
      </div>
    </section>

    <footer class="display-footer">
      <span class="live-line"><span class="live-dot" /> {{ loading ? '正在更新' : '自动刷新中' }}</span>
      <span v-if="error" class="error-line">{{ error }}</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getQueueStatus } from '../api'
import pollingManager from '../utils/pollingManager'

const route = useRoute()
const tenantId = computed(() => String(route.query.tenant_id || localStorage.getItem('tenant_id') || '1'))
const status = ref({})
const loading = ref(false)
const error = ref('')
const now = ref(new Date())
let clock = null

const dateText = computed(() => now.value.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', weekday: 'short' }))
const timeText = computed(() => now.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }))

function unwrap(res) {
  if (res?.success === false) throw new Error(res.message || '加载失败')
  return res?.data || res
}

async function load(pollMeta = {}) {
  loading.value = true
  error.value = ''
  try {
    status.value = unwrap(await getQueueStatus({ tenant_id: tenantId.value }, { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'queue:status:' + tenantId.value } })) || {}
  } catch (err) {
    error.value = err?.message || '排位数据加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  pollingManager.start('queue-display:status', {
    task: load,
    interval: 20000,
    hiddenInterval: 120000,
    idleInterval: 90000,
    immediate: false,
  })
  clock = setInterval(() => { now.value = new Date() }, 1000)
})

onBeforeUnmount(() => {
  pollingManager.stop('queue-display:status')
  clearInterval(clock)
})
</script>

<style scoped>
/* 基础 .animate-in 用全局 global.scss 定义；这里只保留大屏专属的、放大版
   呼吸点样式（10px + 光晕，比手机端 6px 的更适合远距离观看电视大屏）。
   这是常亮电视大屏，配色固定深色，不跟随 prefers-color-scheme。 */
@keyframes queueLivePulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .45; transform: scale(.8); }
}
.live-dot {
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--brand);
  box-shadow: 0 0 0 4px rgba(7,193,96,.2);
  animation: queueLivePulse 1.6s ease-in-out infinite;
  vertical-align: middle;
  margin-right: 8px;
}
.live-line { display: inline-flex; align-items: center; }

.display-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 40px 48px 32px;
  background: var(--hero-dark);
  color: #ffffff;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  gap: 28px;
}
.display-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 32px;
}
.brand { font-size: clamp(28px, 3vw, 48px); line-height: 1; font-weight: 900; letter-spacing: 0; }
.subline { margin-top: 12px; font-size: clamp(16px, 1.4vw, 24px); color: #a3a3a3; font-weight: 700; }
.time-block { text-align: right; flex-shrink: 0; }
.time-block strong { display: block; font-size: clamp(32px, 4vw, 64px); line-height: .95; font-weight: 900; color: #f5f5f5; }
.time-block span { display: block; margin-top: 10px; font-size: clamp(15px, 1.2vw, 22px); color: #a3a3a3; font-weight: 800; }
.hero-panel {
  position: relative;
  overflow: hidden;
  min-height: 380px;
  border-radius: 24px;
  background: #ffffff;
  color: #111111;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  box-shadow: 0 28px 80px rgb(0 0 0 / .28);
}
.hero-panel::before {
  content: '';
  position: absolute;
  top: -120px; right: -100px;
  width: 320px; height: 320px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(7,193,96,.12), transparent 70%);
}
.hero-label { font-size: clamp(28px, 3vw, 52px); line-height: 1; color: #606060; font-weight: 900; }
.current-number {
  margin-top: 28px;
  font-size: clamp(112px, 18vw, 260px);
  line-height: .9;
  font-weight: 1000;
  color: var(--danger);
  letter-spacing: 0;
  white-space: nowrap;
}
.current-number.empty { font-size: clamp(72px, 10vw, 150px); color: #2a2a2a; }
.next-line { margin-top: 30px; font-size: clamp(28px, 3vw, 56px); line-height: 1.1; font-weight: 900; color: #1f1f1f; }
.count-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.count-item {
  min-height: 150px;
  border-radius: 18px;
  background: #1b1b1b;
  border: 1px solid rgb(255 255 255 / .14);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 30px;
}
.count-item span { color: #d4d4d4; font-size: clamp(22px, 2vw, 34px); font-weight: 900; }
.count-item strong { color: #ffffff; font-size: clamp(64px, 7vw, 118px); line-height: 1; font-weight: 1000; }
.display-footer { display: flex; justify-content: space-between; gap: 20px; color: #8a8a8a; font-size: 18px; font-weight: 800; }
.error-line { color: #fca5a5; }
@media (max-width: 768px) {
  .display-page { padding: 24px 18px; gap: 18px; }
  .display-header { align-items: flex-start; }
  .subline { display: none; }
  .hero-panel { min-height: 320px; border-radius: 18px; }
  .current-number { font-size: clamp(86px, 25vw, 128px); }
  .current-number.empty { font-size: 54px; }
  .count-row { grid-template-columns: 1fr; gap: 12px; }
  .count-item { min-height: 96px; padding: 18px 20px; }
  .display-footer { font-size: 13px; }
}
</style>



