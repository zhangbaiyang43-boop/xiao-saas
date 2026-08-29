<template>
  <div class="demo-page">
    <main class="demo-shell">
      <section v-if="phase === 'loading'" class="state-card">
        <a-spin size="large" />
        <h1>正在准备本次体验</h1>
        <p>马上为你生成专属顾客点餐码</p>
      </section>

      <section v-else-if="phase === 'error'" class="state-card">
        <div class="state-mark state-mark--error">!</div>
        <h1>体验暂时没有启动</h1>
        <p>{{ errorMessage }}</p>
        <a-button type="primary" block class="main-button" @click="restartDemo">
          重新开始30分钟体验
        </a-button>
      </section>

      <section v-else-if="phase === 'expired'" class="state-card">
        <div class="state-mark">30</div>
        <h1>本次体验已结束</h1>
        <p>为保护每家商户的数据，本次订单窗口已经关闭</p>
        <a-button type="primary" block class="main-button" @click="restartDemo">
          重新开始30分钟体验
        </a-button>
      </section>

      <template v-else>
        <header class="demo-header">
          <div>
            <div class="eyebrow">开心点单 · 商家体验台</div>
            <h1>{{ session?.shopName || '开心点单体验店' }}</h1>
          </div>
          <div class="countdown">
            <span>剩余</span>
            <strong>{{ remainingLabel }}</strong>
          </div>
        </header>

        <a-alert
          v-if="syncFailed"
          type="warning"
          show-icon
          message="订单可能不是最新，请检查网络后重试"
          class="sync-alert"
        />

        <a-card :bordered="false" class="qr-card">
          <div class="section-kicker">第 1 步</div>
          <h2>请用另一台手机扫描</h2>
          <p>进入顾客小程序，选菜并提交订单</p>
          <div class="qr-frame">
            <img
              v-if="session?.customerCodeImageUrl"
              :src="customerCodeImageUrl"
              alt="顾客点餐小程序码"
            />
            <a-empty v-else description="顾客点餐码暂未生成" />
          </div>
          <div class="table-chip">本次体验桌号 {{ session?.tableNo || '-' }}</div>
          <div class="flow-strip">
            <span>顾客下单</span><b>→</b><span>商家接单</span><b>→</b><span>完成上菜</span>
          </div>
        </a-card>

        <section class="orders-section">
          <div class="section-head">
            <div>
              <div class="section-kicker">第 2 步</div>
              <h2>处理真实体验订单</h2>
            </div>
            <a-tag color="green">每2秒同步</a-tag>
          </div>

          <a-empty
            v-if="orders.length === 0"
            class="empty-card"
            description="请用另一台手机扫描上方顾客点餐码，提交后订单会自动出现在这里"
          />

          <a-card
            v-for="order in orders"
            :key="order.orderId"
            :bordered="false"
            class="order-card"
          >
            <div class="order-top">
              <div>
                <strong>#{{ order.displayOrderNo }}</strong>
                <span>{{ formatTime(order.createdAt) }}</span>
              </div>
              <a-tag :color="statusColor(order)">{{ statusLabel(order) }}</a-tag>
            </div>

            <div class="items-list">
              <div v-for="item in order.items" :key="`${order.orderId}-${item.name}`" class="item-row">
                <div>
                  <strong>{{ item.name }}</strong>
                  <small v-if="item.remark">{{ item.remark }}</small>
                </div>
                <b>×{{ item.quantity }}</b>
              </div>
            </div>

            <div v-if="order.remark" class="order-remark">备注：{{ order.remark }}</div>

            <a-button
              v-if="nextDemoAction(order)"
              type="primary"
              block
              class="order-action"
              :loading="actionOrderId === order.orderId"
              @click="performOrderAction(order)"
            >
              {{ nextDemoAction(order).label }}
            </a-button>
            <div v-else class="order-finished">本单体验流程已完成</div>
          </a-card>
        </section>

        <footer class="demo-footer">
          本次只展示扫码点单和商家履约流程，{{ remainingLabel }} 后自动结束
        </footer>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'

import {
  getDemoSession,
  serveDemoOrder,
  startDemoSession,
  updateDemoOrderStatus,
} from '../api/demo'
import {
  clearDemoSession,
  nextDemoAction,
  parseServerTime,
  readDemoSession,
  saveDemoSession,
} from '../demo/session'


const route = useRoute()
const phase = ref('loading')
const session = ref(null)
const orders = ref([])
const syncFailed = ref(false)
const actionOrderId = ref('')
const remainingSeconds = ref(0)
const errorMessage = ref('请检查网络后重试')
let pollTimer = null
let countdownTimer = null
let syncing = false

const launchCode = computed(() => String(route.query.launchCode || '').trim())
const remainingLabel = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60)
  const seconds = remainingSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
const customerCodeImageUrl = computed(() => {
  const url = session.value?.customerCodeImageUrl || ''
  if (!url || url.startsWith('http')) return url
  return `${import.meta.env.VITE_API_ORIGIN || 'https://api.zhangbaiyang.com'}${url}`
})

function unwrap(response) {
  if (response?.code !== 200) throw new Error(response?.msg || '体验请求失败')
  return response.data
}

function readableStartError(error) {
  const backendMessage = error.response?.data?.msg || error.response?.data?.message
  if (backendMessage) return backendMessage
  if (error.response?.status === 404) return '体验码无效或已过期，请重新扫描体验卡'
  if (!error.response) return '暂时无法连接体验服务，请检查网络后重试'
  return '体验暂时无法启动，请重新扫描体验卡'
}

function clearTimers() {
  if (pollTimer) clearInterval(pollTimer)
  if (countdownTimer) clearInterval(countdownTimer)
  pollTimer = null
  countdownTimer = null
}

function updateCountdown() {
  const expiresAt = parseServerTime(session.value?.expiresAt)
  if (!Number.isFinite(expiresAt)) {
    remainingSeconds.value = 0
    return
  }
  remainingSeconds.value = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000))
  if (remainingSeconds.value === 0) {
    clearTimers()
    clearDemoSession(sessionStorage)
    phase.value = 'expired'
  }
}

async function refreshSnapshot() {
  if (syncing || phase.value !== 'ready') return
  syncing = true
  try {
    const data = unwrap(await getDemoSession())
    orders.value = Array.isArray(data?.orders) ? data.orders : []
    syncFailed.value = false
  } catch (error) {
    syncFailed.value = true
    if ([401, 403].includes(error.response?.status)) {
      clearTimers()
      phase.value = 'expired'
    }
  } finally {
    syncing = false
  }
}

function startTimers() {
  clearTimers()
  updateCountdown()
  pollTimer = setInterval(refreshSnapshot, 2000)
  countdownTimer = setInterval(updateCountdown, 1000)
}

async function prepareDemo() {
  phase.value = 'loading'
  errorMessage.value = '请检查网络后重试'
  try {
    let activeSession = readDemoSession(sessionStorage)
    if (!activeSession) {
      if (!launchCode.value) throw new Error('体验链接缺少启动凭证，请重新扫描体验卡')
      activeSession = unwrap(await startDemoSession(launchCode.value))
      saveDemoSession(sessionStorage, activeSession)
    }
    session.value = activeSession
    phase.value = 'ready'
    startTimers()
    await refreshSnapshot()
  } catch (error) {
    clearTimers()
    errorMessage.value = readableStartError(error)
    phase.value = 'error'
  }
}

async function restartDemo() {
  clearDemoSession(sessionStorage)
  session.value = null
  orders.value = []
  syncFailed.value = false
  await prepareDemo()
}

async function performOrderAction(order) {
  const action = nextDemoAction(order)
  if (!action || actionOrderId.value) return
  actionOrderId.value = order.orderId
  try {
    if (action.serve) {
      unwrap(await serveDemoOrder(order.orderId))
    } else {
      unwrap(await updateDemoOrderStatus(order.orderId, action.status))
    }
    await refreshSnapshot()
    message.success(`${action.label}成功`)
  } catch (error) {
    message.error(error.response?.data?.msg || error.message || '操作失败，请重试')
  } finally {
    actionOrderId.value = ''
  }
}

function statusLabel(order) {
  if (order.status === 'pending') return '待接单'
  if (order.status === 'preparing') return '制作中'
  if (order.status === 'done' && !order.servedAt) return '待上菜'
  if (order.status === 'done' && order.servedAt) return '已上菜'
  return '处理中'
}

function statusColor(order) {
  if (order.status === 'pending') return 'red'
  if (order.status === 'preparing') return 'blue'
  return 'green'
}

function formatTime(value) {
  const date = new Date(parseServerTime(value))
  if (!value || Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

onMounted(prepareDemo)
onBeforeUnmount(clearTimers)
</script>

<style scoped>
.demo-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 14px;
  background: #f5f7f9;
  color: #1f2937;
}

.demo-shell {
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
}

.demo-header,
.section-head,
.order-top,
.item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.demo-header {
  padding: 6px 2px 14px;
}

.demo-header h1,
.section-head h2,
.qr-card h2,
.state-card h1 {
  margin: 0;
  color: #111827;
}

.demo-header h1 { margin-top: 3px; font-size: 21px; font-weight: 900; }
.eyebrow,
.section-kicker { color: #6b7280; font-size: 12px; font-weight: 700; }
.countdown { min-width: 72px; padding: 7px 10px; border-radius: 12px; background: #fff; text-align: center; }
.countdown span { display: block; color: #9ca3af; font-size: 10px; }
.countdown strong { color: #07c160; font-size: 18px; font-variant-numeric: tabular-nums; }
.sync-alert { margin-bottom: 12px; border-radius: 12px; }

.qr-card,
.order-card,
.empty-card,
.state-card {
  border-radius: 16px;
  box-shadow: 0 5px 18px rgba(15, 23, 42, .06);
}

.qr-card { text-align: center; }
.qr-card h2 { margin-top: 4px; font-size: 21px; font-weight: 900; }
.qr-card p { margin: 5px 0 14px; color: #6b7280; font-size: 13px; }
.qr-frame { width: 214px; min-height: 214px; margin: 0 auto; padding: 9px; box-sizing: border-box; border: 2px solid #07c160; border-radius: 16px; background: #fff; }
.qr-frame img { display: block; width: 100%; height: auto; border-radius: 8px; }
.table-chip { display: inline-flex; margin-top: 12px; padding: 6px 12px; border-radius: 999px; background: #ecfdf5; color: #047857; font-weight: 800; font-size: 13px; }
.flow-strip { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 14px; color: #374151; font-size: 12px; font-weight: 700; }
.flow-strip b { color: #07c160; }

.orders-section { margin-top: 16px; }
.section-head { padding: 0 2px 10px; }
.section-head h2 { margin-top: 2px; font-size: 18px; font-weight: 900; }
.empty-card { padding: 22px 4px; background: #fff; }
.order-card { margin-bottom: 12px; }
.order-top { margin-bottom: 13px; }
.order-top > div { display: flex; align-items: baseline; gap: 8px; }
.order-top strong { font-size: 18px; }
.order-top span { color: #9ca3af; font-size: 12px; }
.items-list { border-top: 1px solid #eef0f2; }
.item-row { min-height: 54px; border-bottom: 1px solid #eef0f2; }
.item-row > div { min-width: 0; }
.item-row strong { display: block; font-size: 17px; }
.item-row small { display: block; margin-top: 3px; color: #b45309; font-size: 12px; }
.item-row b { flex-shrink: 0; color: #07c160; font-size: 18px; }
.order-remark { margin-top: 10px; padding: 9px 10px; border-radius: 10px; background: #fffbeb; color: #92400e; font-size: 13px; font-weight: 700; }
.order-action,
.main-button { min-height: 48px; margin-top: 14px; border-radius: 12px; font-size: 17px; font-weight: 900; }
.order-finished { margin-top: 12px; padding: 11px; border-radius: 10px; background: #ecfdf5; color: #047857; text-align: center; font-weight: 800; }
.demo-footer { padding: 10px 6px 18px; color: #9ca3af; text-align: center; font-size: 12px; line-height: 1.6; }

.state-card { margin-top: 34px; padding: 34px 22px; background: #fff; text-align: center; }
.state-card h1 { margin-top: 15px; font-size: 21px; font-weight: 900; }
.state-card p { margin: 8px 0 0; color: #6b7280; line-height: 1.6; }
.state-mark { display: flex; align-items: center; justify-content: center; width: 58px; height: 58px; margin: 0 auto; border-radius: 50%; background: #ecfdf5; color: #047857; font-size: 20px; font-weight: 900; }
.state-mark--error { background: #fef2f2; color: #dc2626; font-size: 30px; }

@media (min-width: 768px) {
  .demo-page { padding-top: 26px; }
}
</style>
