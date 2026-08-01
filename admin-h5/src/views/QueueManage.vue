<template>
  <div class="queue-page">
    <div class="queue-header">
      <div>
        <div class="queue-title">排位管理</div>
        <div class="queue-subtitle">取号 · 叫号 · 入座 · 过号</div>
      </div>
      <a-button type="text" aria-label="刷新" :loading="loading" @click="loadAll">
        <template #icon><ReloadOutlined /></template>
      </a-button>
    </div>

    <div class="summary-band animate-in">
      <div class="summary-main">
        <span>当前叫号</span>
        <strong>{{ status.current_called || '暂无' }}</strong>
      </div>
      <div class="summary-side">
        <span>等待人数</span>
        <strong>{{ status.waiting_count || 0 }}</strong>
      </div>
    </div>

    <div class="quick-actions animate-in" style="animation-delay:.04s">
      <a-button class="take-btn take-a tap-shrink" :loading="creatingType === 'A'" @click="quickTake('A')">取小桌号</a-button>
      <a-button class="take-btn take-b tap-shrink" :loading="creatingType === 'B'" @click="quickTake('B')">取中桌号</a-button>
      <a-button class="take-btn take-c tap-shrink" :loading="creatingType === 'C'" @click="quickTake('C')">取大桌号</a-button>
    </div>

    <div class="call-panel animate-in" style="animation-delay:.08s">
      <div class="call-title">叫下一位</div>
      <div class="call-buttons">
        <a-button v-for="type in queueTypes" :key="type.key" class="call-btn" :disabled="isCallDisabled(type.key)" :loading="callingType === type.key" @click="callNext(type.key)">
          {{ callButtonText(type) }}
        </a-button>
      </div>
    </div>

    <a-alert v-if="error" type="error" show-icon :message="error" class="page-alert" />

    <div v-if="loading && tickets.length === 0" class="loading-wrap">
      <a-skeleton active :paragraph="{ rows: 6 }" />
    </div>

    <div v-else class="queue-groups">
      <section v-for="type in queueTypes" :key="type.key" class="queue-section">
        <div class="section-head">
          <div>
            <div class="section-title">{{ type.title }}</div>
            <div class="section-desc">{{ type.desc }}</div>
          </div>
          <div class="count-pill">{{ sectionCountText(type.key) }}</div>
        </div>

        <div v-if="groupedTickets[type.key].length === 0" class="empty-box">暂无等待</div>

        <div v-for="ticket in groupedTickets[type.key]" :key="ticket.id" class="ticket-card" :class="`status-${ticket.status}`">
          <div class="ticket-main">
            <div>
              <div class="queue-no">{{ ticket.queue_no }}</div>
              <div class="ticket-meta">
                {{ ticket.party_size }}人
                <span v-if="ticket.phone_tail"> · 尾号{{ ticket.phone_tail }}</span>
                · 等待{{ ticket.wait_minutes || 0 }}分钟
              </div>
            </div>
            <span class="status-tag">{{ statusText(ticket.status) }}</span>
          </div>
          <div v-if="ticket.note" class="ticket-note">{{ ticket.note }}</div>
          <div class="ticket-actions">
            <a-button size="large" type="primary" :loading="updatingId === ticket.id + ':seat'" @click="seatTicket(ticket)">入座</a-button>
            <a-button size="large" danger :loading="updatingId === ticket.id + ':skip'" @click="skipTicket(ticket)">过号</a-button>
          </div>
        </div>
      </section>
    </div>

    <div class="bottom-space" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { callNextQueueTicket, createQueueTicket, getQueueStatus, getQueueTickets, seatQueueTicket, skipQueueTicket } from '../api'

function decodeJwtPayload(token) {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(window.atob(normalized))
  } catch {
    return null
  }
}

function getCurrentTenantId() {
  const tokenPayload = decodeJwtPayload(localStorage.getItem('token') || '')
  return String(tokenPayload?.tenant_id || localStorage.getItem('tenant_id') || '1')
}

const tenantId = getCurrentTenantId()
const loading = ref(false)
const tickets = ref([])
const status = ref({})
const error = ref('')
const creatingType = ref('')
const callingType = ref('')
const updatingId = ref('')

const queueTypes = [
  { key: 'A', label: '小桌', title: '小桌等待队列', desc: '1-2人' },
  { key: 'B', label: '中桌', title: '中桌等待队列', desc: '3-4人' },
  { key: 'C', label: '大桌', title: '大桌等待队列', desc: '5人以上' },
]

const waitingCounts = computed(() => ({
  A: tickets.value.filter(t => t.queue_type === 'A' && t.status === 'waiting').length,
  B: tickets.value.filter(t => t.queue_type === 'B' && t.status === 'waiting').length,
  C: tickets.value.filter(t => t.queue_type === 'C' && t.status === 'waiting').length,
}))
const calledCounts = computed(() => ({
  A: tickets.value.filter(t => t.queue_type === 'A' && t.status === 'called').length,
  B: tickets.value.filter(t => t.queue_type === 'B' && t.status === 'called').length,
  C: tickets.value.filter(t => t.queue_type === 'C' && t.status === 'called').length,
}))
const groupedTickets = computed(() => {
  const groups = { A: [], B: [], C: [] }
  tickets.value
    .filter(t => ['waiting', 'called'].includes(t.status))
    .forEach(t => {
      if (groups[t.queue_type]) groups[t.queue_type].push(t)
    })
  return groups
})

function isCallDisabled(type) {
  return waitingCounts.value[type] === 0 || calledCounts.value[type] > 0
}

function callButtonText(type) {
  if (calledCounts.value[type.key] > 0) return `${type.label}先处理已叫号`
  if (waitingCounts.value[type.key] === 0) return `${type.label}暂无待叫`
  return `${type.label}下一位`
}

function sectionCountText(type) {
  const called = calledCounts.value[type]
  const waiting = waitingCounts.value[type]
  return called > 0 ? `${waiting}桌待叫 · ${called}桌叫中` : `${waiting}桌待叫`
}
function unwrap(res) {
  if (res?.success === false) throw new Error(res.message || '操作失败')
  return res?.data || res
}

function statusText(value) {
  return { waiting: '等待中', called: '已叫号', seated: '已入座', skipped: '已过号', cancelled: '已取消' }[value] || value
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [statusRes, ticketsRes] = await Promise.all([
      getQueueStatus({ tenant_id: tenantId }),
      getQueueTickets({ tenant_id: tenantId }),
    ])
    status.value = unwrap(statusRes) || {}
    tickets.value = Array.isArray(unwrap(ticketsRes)) ? unwrap(ticketsRes) : []
  } catch (err) {
    error.value = err?.message || '排位数据加载失败'
  } finally {
    loading.value = false
  }
}

async function quickTake(type) {
  const partySize = { A: 2, B: 4, C: 6 }[type]
  creatingType.value = type
  try {
    const data = unwrap(await createQueueTicket({ tenant_id: tenantId, party_size: partySize }))
    message.success(`已取号 ${data.queue_no}`)
    await loadAll()
  } catch (err) {
    message.error(err?.message || '取号失败')
  } finally {
    creatingType.value = ''
  }
}

async function callNext(type) {
  if (calledCounts.value[type] > 0) {
    message.info('请先入座或过号当前叫号')
    return
  }
  if (waitingCounts.value[type] === 0) {
    message.info('该队列暂无等待号')
    return
  }
  callingType.value = type
  try {
    const data = unwrap(await callNextQueueTicket({ tenant_id: tenantId, queue_type: type }))
    message.success(`正在叫号 ${data.queue_no}`)
    await loadAll()
  } catch (err) {
    message.error(err?.message || '叫号失败')
  } finally {
    callingType.value = ''
  }
}

async function seatTicket(ticket) {
  updatingId.value = `${ticket.id}:seat`
  try {
    unwrap(await seatQueueTicket(ticket.id, { tenant_id: tenantId }))
    message.success(`${ticket.queue_no} 已入座`)
    await loadAll()
  } catch (err) {
    message.error(err?.message || '入座失败')
  } finally {
    updatingId.value = ''
  }
}

async function skipTicket(ticket) {
  updatingId.value = `${ticket.id}:skip`
  try {
    unwrap(await skipQueueTicket(ticket.id, { tenant_id: tenantId }))
    message.success(`${ticket.queue_no} 已过号`)
    await loadAll()
  } catch (err) {
    message.error(err?.message || '过号失败')
  } finally {
    updatingId.value = ''
  }
}

onMounted(loadAll)
</script>

<style scoped>
.queue-page { min-height: 100vh; background: var(--bg-page); }
.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 52px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.queue-title { font-size: 20px; font-weight: 900; color: var(--text-1); }
.queue-subtitle { margin-top: 2px; font-size: 12px; color: var(--text-3); }
.summary-band {
  display: grid;
  grid-template-columns: 1fr 112px;
  gap: 10px;
  padding: 12px 16px 0;
}
.summary-main, .summary-side {
  min-height: 88px;
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--card-shadow);
  padding: 14px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.summary-main span, .summary-side span { font-size: 13px; color: var(--text-2); }
.summary-main strong { margin-top: 6px; font-size: 42px; line-height: 1; color: #ef4444; }
.summary-side strong { margin-top: 6px; font-size: 32px; line-height: 1; color: var(--text-1); }
.quick-actions, .call-buttons {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.quick-actions { padding: 12px 16px 0; }
.take-btn, .call-btn { height: 52px; border-radius: 12px; font-weight: 800; font-size: 15px; }
.take-a { background: #07c160; border-color: #07c160; color: #fff; }
.take-b { background: #1677ff; border-color: #1677ff; color: #fff; }
.take-c { background: #ff7a00; border-color: #ff7a00; color: #fff; }
.call-panel { margin: 12px 16px 0; padding: 12px; border-radius: 12px; background: var(--bg-card); box-shadow: var(--card-shadow); }
.call-title { margin-bottom: 10px; font-size: 14px; font-weight: 800; color: var(--text-1); }
.page-alert { margin: 12px 16px 0; border-radius: 10px; }
.loading-wrap { margin: 12px 16px 0; padding: 14px; border-radius: 12px; background: var(--bg-card); }
.queue-section { margin: 12px 16px 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-size: 16px; font-weight: 900; color: var(--text-1); }
.section-desc { margin-top: 1px; font-size: 12px; color: var(--text-3); }
.count-pill { padding: 4px 10px; border-radius: 999px; background: var(--bg-card); box-shadow: var(--card-shadow); color: var(--text-2); font-size: 12px; font-weight: 800; }
.empty-box { padding: 18px; border-radius: 12px; background: var(--bg-card); text-align: center; color: var(--text-3); }
.ticket-card { margin-bottom: 8px; padding: 14px; border-radius: 12px; background: var(--bg-card); box-shadow: var(--card-shadow); border-left: 5px solid var(--border); }
.ticket-card.status-called { border-left-color: #ef4444; }
.ticket-main { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.queue-no { font-size: 30px; line-height: 1; font-weight: 900; color: var(--text-1); }
.ticket-meta { margin-top: 6px; font-size: 13px; color: var(--text-2); }
.status-tag { flex-shrink: 0; padding: 4px 9px; border-radius: 999px; background: var(--bg-page); color: var(--text-2); font-size: 12px; font-weight: 800; }
.status-called .status-tag { background: #fef2f2; color: #ef4444; }
.ticket-note { margin-top: 8px; padding: 8px; border-radius: 8px; background: #fffbeb; color: #92400e; font-size: 12px; }
.ticket-actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 12px; }
.ticket-actions :deep(.ant-btn) { height: 44px; border-radius: 10px; font-weight: 800; }
.bottom-space { height: 84px; }
@media (max-width: 360px) {
  .summary-band { grid-template-columns: 1fr; }
  .quick-actions, .call-buttons { grid-template-columns: 1fr; }
}
</style>









