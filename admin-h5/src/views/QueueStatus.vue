<template>
  <div class="queue-status-page">
    <main class="status-shell">
      <section v-if="loading && !ticket" class="state-card animate-in">
        <div class="spinner" />
        <h1>正在查询排队进度</h1>
        <p>请稍候</p>
      </section>

      <section v-else-if="invalid" class="state-card animate-in">
        <div class="invalid-icon">!</div>
        <h1>排队查询已失效</h1>
        <p>{{ error || '请联系门店前台确认当前排队状态' }}</p>
      </section>

      <template v-else-if="ticket">
        <section class="shop-head animate-in">
          <span>{{ ticket.shop_name || '门店排队' }}</span>
          <strong>{{ ticket.status_text || statusText }}</strong>
        </section>

        <section class="number-card animate-in" :class="statusClass">
          <div class="label">排队号码</div>
          <div class="number">{{ ticket.queue_number || ticket.queue_no }}</div>
          <div class="meta-row">
            <span>{{ ticket.queue_type_name || '-' }}</span>
            <span>{{ ticket.party_size_text || ((ticket.party_size || '-') + '人') }}</span>
          </div>
        </section>

        <section class="progress-card animate-in">
          <div class="wait-main">
            <span>前方等待</span>
            <strong>{{ ticket.ahead_count ?? 0 }}</strong>
            <span>桌</span>
          </div>
          <div class="estimate">预计等待 {{ ticket.estimated_wait_text || '-' }}</div>
        </section>

        <section class="detail-card animate-in">
          <div class="detail-row">
            <span>当前状态</span>
            <strong>{{ ticket.status_text || statusText }}</strong>
          </div>
          <div class="detail-row">
            <span>取号时间</span>
            <strong>{{ ticket.created_at_text || formatTime(ticket.created_at) }}</strong>
          </div>
          <div class="detail-row detail-row--tip">
            <span>过号提示</span>
            <strong>{{ ticket.skipped_tip || '过号请联系前台处理' }}</strong>
          </div>
        </section>

        <footer class="refresh-line">
          <span class="live-line"><span v-if="!isFinal" class="live-dot" />{{ pollingLabel }}</span>
          <button type="button" class="tap-shrink" :disabled="loading" @click="loadStatus(true)">{{ loading ? '刷新中' : '手动刷新' }}</button>
        </footer>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getQueueTicketStatusByToken } from '../api'
import { formatBeijingDateTime } from '../utils/beijingTime'

const route = useRoute()
const token = computed(() => String(route.query.token || '').trim())
const ticket = ref(null)
const loading = ref(false)
const invalid = ref(false)
const error = ref('')
const failCount = ref(0)
const lastUpdatedAt = ref(null)
let timer = null

const finalStatuses = new Set(['seated', 'cancelled', 'skipped'])
const nearStatuses = new Set(['called'])
const statusTextMap = {
  waiting: '等待中',
  called: '已叫号',
  seated: '已就餐',
  skipped: '已过号',
  cancelled: '已取消',
}

const statusText = computed(() => statusTextMap[ticket.value?.status] || ticket.value?.status || '-')
const statusClass = computed(() => `number-card--${ticket.value?.status || 'waiting'}`)
const isFinal = computed(() => finalStatuses.has(ticket.value?.status))
const isNear = computed(() => nearStatuses.has(ticket.value?.status) || Number(ticket.value?.ahead_count || 0) <= 1)
const pollingLabel = computed(() => {
  if (isFinal.value) return '当前状态已结束，已停止自动刷新'
  if (!lastUpdatedAt.value) return '自动刷新已开启'
  return `上次更新 ${lastUpdatedAt.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}`
})

function unwrap(res) {
  if (res?.success === false) throw new Error(res.message || '排队查询已失效')
  return res?.data || res
}

function clearPoll() {
  if (timer) clearTimeout(timer)
  timer = null
}

function nextDelay() {
  const base = isNear.value ? 5000 : 10000
  if (!failCount.value) return base
  return Math.min(base * (2 ** failCount.value), 60000)
}

function schedulePoll() {
  clearPoll()
  if (document.hidden || invalid.value || isFinal.value) return
  timer = setTimeout(() => loadStatus(false), nextDelay())
}

async function loadStatus(manual = false) {
  if (!token.value) {
    invalid.value = true
    error.value = '二维码缺少查询参数'
    return
  }
  loading.value = true
  try {
    const data = unwrap(await getQueueTicketStatusByToken(token.value, { meta: { fromPolling: !manual, dedupe: true, dedupeKey: `queue:ticket:${token.value}` } }))
    ticket.value = data
    invalid.value = false
    error.value = ''
    failCount.value = 0
    lastUpdatedAt.value = new Date()
  } catch (err) {
    if (!ticket.value) invalid.value = true
    error.value = err?.message || '排队查询已失效'
    failCount.value += 1
  } finally {
    loading.value = false
    schedulePoll()
  }
}

function handleVisibilityChange() {
  if (document.hidden) clearPoll()
  else if (!isFinal.value) loadStatus(false)
}

function formatTime(value) {
  if (!value) return '-'
  return formatBeijingDateTime(value) || value
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  loadStatus(true)
})

onBeforeUnmount(() => {
  clearPoll()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped>
/* 基础 .animate-in / .tap-shrink 用全局 global.scss 定义；这里只加错落延迟
   和这个页面专属的、稍微放大的呼吸点样式（手机顾客页比大屏更小巧）。 */
.animate-in:nth-of-type(2) { animation-delay: .05s; }
.animate-in:nth-of-type(3) { animation-delay: .1s; }
.animate-in:nth-of-type(4) { animation-delay: .15s; }
@keyframes queueStatusLivePulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .45; transform: scale(.8); }
}
.live-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--brand);
  box-shadow: 0 0 0 3px rgba(7,193,96,.18);
  animation: queueStatusLivePulse 1.6s ease-in-out infinite;
  margin-right: 6px;
}
.live-line { display: inline-flex; align-items: center; }

.queue-status-page {
  min-height: 100vh;
  background: var(--bg-page);
  padding: 14px;
  box-sizing: border-box;
}
.status-shell { max-width: 480px; margin: 0 auto; }
.shop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 2px 14px;
  color: var(--text-1);
}
.shop-head span { font-size: 18px; font-weight: 800; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shop-head strong { flex-shrink: 0; font-size: 13px; color: var(--success); background: var(--brand-light); border-radius: 999px; padding: 5px 10px; }
.number-card,
.progress-card,
.detail-card,
.state-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  box-shadow: 0 4px 16px rgba(15, 23, 42, .06);
}
.number-card { padding: 22px 18px; text-align: center; }
.label { font-size: 13px; color: var(--text-2); font-weight: 700; }
.number { margin-top: 8px; font-size: 72px; line-height: 1; font-weight: 1000; color: var(--danger); letter-spacing: 0; }
.number-card--called .number { color: var(--brand); }
.number-card--seated .number,
.number-card--skipped .number,
.number-card--cancelled .number { color: var(--text-2); }
.meta-row { display: flex; justify-content: center; gap: 10px; margin-top: 16px; }
.meta-row span { min-width: 76px; padding: 7px 12px; border-radius: 999px; background: #f3f4f6; color: var(--text-1); font-weight: 800; font-size: 14px; }
.progress-card { margin-top: 12px; padding: 18px; }
.wait-main { display: flex; align-items: baseline; justify-content: center; gap: 8px; color: var(--text-1); }
.wait-main span { font-size: 15px; color: var(--text-2); font-weight: 700; }
.wait-main strong { font-size: 48px; line-height: 1; color: var(--text-1); font-weight: 1000; }
.estimate { margin-top: 10px; text-align: center; color: var(--brand); font-size: 15px; font-weight: 800; }
.detail-card { margin-top: 12px; padding: 0 16px; }
.detail-row { min-height: 50px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--border); }
.detail-row:last-child { border-bottom: none; }
.detail-row span { color: var(--text-2); font-size: 14px; }
.detail-row strong { color: var(--text-1); font-size: 14px; text-align: right; }
.detail-row--tip strong { color: var(--danger); }
.refresh-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 2px; font-size: 12px; color: var(--text-3); }
.refresh-line button { border: none; border-radius: 999px; background: var(--brand); color: #fff; padding: 8px 14px; font-weight: 800; }
.refresh-line button:disabled { opacity: .6; }
.state-card { margin-top: 28px; padding: 34px 22px; text-align: center; }
.state-card h1 { margin: 14px 0 8px; font-size: 20px; color: var(--text-1); }
.state-card p { margin: 0; color: var(--text-2); line-height: 1.6; }
.invalid-icon { width: 52px; height: 52px; margin: 0 auto; border-radius: 50%; background: #fee2e2; color: var(--danger); display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 900; }
.spinner { width: 44px; height: 44px; margin: 0 auto; border-radius: 50%; border: 4px solid var(--border); border-top-color: var(--brand); animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (min-width: 768px) {
  .queue-status-page { padding-top: 28px; }
}
</style>
