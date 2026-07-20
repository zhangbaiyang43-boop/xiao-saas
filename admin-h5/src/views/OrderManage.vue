<template>
  <div class="page-wrap">
    <!-- 页面顶部 -->
    <div class="page-header">
      <div>
        <span class="page-title">接单管理</span>
        <div v-if="lastRefreshed" style="font-size:11px;color:#9ca3af;margin-top:1px">{{ lastRefreshed }} 更新</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <div v-if="alertEnabled" class="alert-on-badge" @click="disableAlert">
          <span class="alert-dot" />提醒开
        </div>
        <a-button v-else size="small" type="primary" ghost @click="enableAlert" style="font-size:12px;height:28px;padding:0 10px">
          开启提醒
        </a-button>
        <a-button type="text" @click="manualRefresh" :loading="loading">
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>

    <!-- 统计数字 -->
    <div style="padding:12px 16px 0">
      <a-card :bordered="false" :body-style="{ padding: '12px 0' }">
        <a-row>
          <a-col :span="6" v-for="s in statItems" :key="s.label" style="text-align:center;padding:4px 0">
            <div :style="{ fontSize: '22px', fontWeight: 900, color: s.color }">{{ s.value }}</div>
            <div style="font-size:11px;color:#9ca3af;margin-top:2px">{{ s.label }}</div>
          </a-col>
        </a-row>
      </a-card>
    </div>

    <!-- 视图切换 -->
    <a-tabs v-model:activeKey="view" style="padding:0 16px;margin-top:8px" :tab-bar-style="{ marginBottom: 0 }">
      <a-tab-pane key="table" tab="桌台视图" />
      <a-tab-pane key="list" tab="订单列表" />
    </a-tabs>

    <!-- 网络警告 -->
    <div v-if="pollFailCount >= 3" style="padding:8px 16px 0">
      <a-alert type="warning" show-icon message="网络连接异常，数据可能不是最新的" style="border-radius:10px">
        <template #action>
          <a-button size="small" @click="manualRefresh">重试</a-button>
        </template>
      </a-alert>
    </div>

    <!-- 骨架屏 -->
    <div v-if="loading && orders.length === 0" style="padding:12px 16px 0">
      <a-skeleton active :paragraph="{ rows: 4 }" style="background:#fff;border-radius:12px;padding:16px;margin-bottom:12px" />
      <a-skeleton active :paragraph="{ rows: 3 }" style="background:#fff;border-radius:12px;padding:16px" />
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading && orders.length === 0" style="padding:48px 0">
      <a-empty description="今天还没有订单，去桌码页面打印桌贴码，贴到桌上后顾客即可扫码点餐">
        <template #image><OrderedListOutlined style="font-size:60px;color:#d1d5db" /></template>
      </a-empty>
    </div>

    <!-- 桌台视图 -->
    <template v-if="view === 'table'">
      <div v-for="table in tableGroups" :key="table.groupKey" style="padding:8px 16px 0">
        <a-card :bordered="false" :body-style="{ padding: 0 }">
          <!-- 桌台标题 -->
          <div class="table-head">
            <div style="display:flex;align-items:center;gap:8px">
              <a-tag :class="`tag-${tableTagClass(table)}`" style="font-size:13px;padding:2px 8px">桌{{ table.tableNo }}</a-tag>
              <span class="table-state">{{ tableStatusText(table) }}</span>
            </div>
            <span class="table-total">¥{{ table.total.toFixed(2) }}</span>
          </div>

          <!-- 订单列表 -->
          <div v-for="order in table.orders" :key="order.id" class="order-row">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <a-tag :class="`tag-${order.status}`" size="small">{{ statusLabel(order.status) }}</a-tag>
                <a-tag v-if="order.source === 'h5'" size="small" style="background:#eff6ff;color:#2563eb;border-color:#bfdbfe;font-size:10px">H5</a-tag>
                <span style="font-size:12px;color:#9ca3af">{{ order.time }}</span>
              </div>
              <div style="text-align:right">
                <div style="font-size:16px;font-weight:700;color:var(--text-1)">¥{{ Number(order.total).toFixed(2) }}</div>
                <div v-if="order.discount_amount" style="font-size:11px;color:#ef4444;margin-top:2px">优惠 -¥{{ Number(order.discount_amount).toFixed(2) }}</div>
              </div>
            </div>
            <div style="font-size:13px;color:#4b5563;margin-bottom:6px">
              {{ order.items.map(i => i.name + '×' + i.qty).join(' · ') }}
            </div>
            <div v-if="order.remark" style="display:flex;align-items:flex-start;gap:6px;font-size:12px;color:#92400e;background:#fffbeb;padding:6px 8px;border-radius:6px;margin-bottom:6px">
              <EditOutlined style="font-size:12px;margin-top:1px;flex-shrink:0" />
              <span>{{ order.remark }}</span>
            </div>
            <div style="display:flex;gap:8px">
              <a-button v-if="order.status === 'pending'" type="primary" :loading="order.updating" @click="acceptOrder(order)" class="order-action-btn">接单</a-button>
              <a-button v-if="order.status === 'pending'" danger :loading="order.updating" @click="rejectOrder(order)" class="order-action-btn order-action-btn--reject">拒单</a-button>
              <a-button v-if="order.status === 'preparing'" :loading="order.updating" @click="finishOrder(order)" class="order-action-btn order-action-btn--finish">出餐完成</a-button>
            </div>
            <div v-if="['preparing','done'].includes(order.status)" class="merchant-note-row">
              <input v-model="order.merchant_note_draft" class="merchant-note-input" placeholder="给顾客留言（如：招牌菜品已售完，换成了清蒸鱼）" maxlength="40" @keyup.enter="sendMerchantNote(order)" />
              <button class="merchant-note-send" @click="sendMerchantNote(order)">发送</button>
            </div>
            <div v-if="reviewsMap[order.id]" class="review-row">
              <span class="review-stars-display">{{ '★'.repeat(reviewsMap[order.id].rating) }}{{ '☆'.repeat(5 - reviewsMap[order.id].rating) }}</span>
              <span class="review-content-text">{{ reviewsMap[order.id].content || '顾客未评价' }}</span>
            </div>
          </div>

          <!-- 桌台操作 -->
          <div v-if="table.pendingOrders.length || table.preparingOrders.length || table.canSettle" class="table-actions">
            <a-button v-if="table.pendingOrders.length" type="primary" :loading="table.updating" @click="acceptTableOrders(table)" class="order-action-btn">
              全部接单 · {{ table.pendingOrders.length }} 单
            </a-button>
            <a-button v-if="table.preparingOrders.length" :loading="table.updating" @click="finishTableOrders(table)" class="order-action-btn order-action-btn--finish">
              全部出餐
            </a-button>
            <a-button v-if="table.canSettle" type="primary" :loading="table.updating" @click="settleTableClick(table)" class="order-action-btn order-action-btn--settle">
              结账 ¥{{ table.total.toFixed(2) }}
            </a-button>
          </div>
          <div v-if="table.isSettled" style="display:flex;align-items:center;gap:4px;padding:8px 16px;color:#16a34a;font-size:13px;font-weight:600">
            <CheckCircleOutlined />已结账
          </div>
        </a-card>
      </div>
    </template>

    <!-- 列表视图 -->
    <template v-else>
      <div style="padding:8px 16px 0;display:flex;gap:8px;flex-wrap:wrap">
        <span
          v-for="f in statusFilters"
          :key="f.val"
          class="filter-chip"
          :class="statusFilter === f.val ? 'filter-chip--active' : ''"
          @click="statusFilter = f.val"
        >{{ f.label }}</span>
      </div>
      <div v-for="order in sortedOrders" :key="order.id" style="padding:8px 16px 0">
        <a-card :bordered="false" :body-style="{ padding: '12px 16px' }">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
            <div style="display:flex;align-items:center;gap:6px">
              <a-tag style="color:#374151;background:#f3f4f6;border-color:#e5e7eb">桌{{ order.table }}</a-tag>
              <a-tag :class="`tag-${order.status}`">{{ statusLabel(order.status) }}</a-tag>
              <span style="font-size:12px;color:#9ca3af">{{ order.time }}</span>
            </div>
            <div style="text-align:right">
              <div style="font-size:16px;font-weight:700;color:var(--text-1)">楼{{ Number(order.total).toFixed(2) }}</div>
              <div v-if="order.discount_amount" style="font-size:11px;color:#ef4444;margin-top:2px">优惠 -楼{{ Number(order.discount_amount).toFixed(2) }}</div>
            </div>
          </div>
          <div style="font-size:13px;color:#4b5563;margin-bottom:6px">{{ order.items.map(i => i.name + '×' + i.qty).join(' · ') }}</div>
          <div v-if="order.remark" style="display:flex;align-items:flex-start;gap:6px;font-size:12px;color:#92400e;background:#fffbeb;padding:6px 8px;border-radius:6px;margin-bottom:6px">
            <EditOutlined style="font-size:12px;margin-top:1px;flex-shrink:0" /><span>{{ order.remark }}</span>
          </div>
          <div style="display:flex;gap:8px">
            <a-button v-if="order.status === 'pending'" type="primary" :loading="order.updating" @click="acceptOrder(order)" class="order-action-btn">接单</a-button>
            <a-button v-if="order.status === 'pending'" danger :loading="order.updating" @click="rejectOrder(order)" class="order-action-btn order-action-btn--reject">鎷</a-button>
            <a-button v-if="order.status === 'preparing'" :loading="order.updating" @click="finishOrder(order)" class="order-action-btn order-action-btn--finish">鍑洪屾垚</a-button>
          </div>
          <div v-if="['preparing','done'].includes(order.status)" class="merchant-note-row">
            <input v-model="order.merchant_note_draft" class="merchant-note-input" placeholder="给顾客留言" maxlength="40" @keyup.enter="sendMerchantNote(order)" />
            <button class="merchant-note-send" @click="sendMerchantNote(order)">发送</button>
          </div>
          <div v-if="reviewsMap[order.id]" class="review-row">
            <span class="review-stars-display">{{ '★'.repeat(reviewsMap[order.id].rating) }}{{ '☆'.repeat(5 - reviewsMap[order.id].rating) }}</span>
            <span class="review-content-text">{{ reviewsMap[order.id].content || '顾客未评价' }}</span>
          </div>
        </a-card>
      </div>
      <div style="height:16px" />
    </template>

    <!-- 结账确认 Modal -->
    <a-modal
      v-model:open="showSettleDialog"
      title="确认结账"
      :footer="null"
      centered
    >
      <div v-if="settlingTable" style="text-align:center;padding:8px 0 16px">
        <div style="font-size:32px;font-weight:900;color:var(--text-1);margin:8px 0">
          ¥{{ settlingTable.total.toFixed(2) }}
        </div>
        <div style="color:#6b7280;font-size:13px;margin-bottom:16px">桌号 {{ settlingTable.tableNo }} · {{ settlingTable.orders.length }} 单合计</div>
        <a-list :data-source="settlingTable.orders" size="small" :split="true" style="text-align:left;margin-bottom:16px">
          <template #renderItem="{ item }">
            <a-list-item>
              <span style="font-size:13px">{{ item.items.map(i => i.name + '×' + i.qty).join(' ') }}</span>
              <template #actions>
                <span style="color:#07C160;font-weight:600">¥{{ Number(item.total).toFixed(2) }}</span>
              </template>
            </a-list-item>
          </template>
        </a-list>
        <a-button type="primary" block size="large" :loading="settling" @click="confirmSettle" style="background:#16a34a;border-color:#16a34a">
          确认收款
        </a-button>
        <a-button block style="margin-top:8px" @click="showSettleDialog = false">取消</a-button>
      </div>
    </a-modal>

    <!-- 账单 Modal（结账成功后显示）-->
    <a-modal
      v-model:open="showReceiptDialog"
      title="结账账单"
      :footer="null"
      centered
    >
      <div v-if="receiptData" style="padding:4px 0 16px">
        <div style="text-align:center;margin-bottom:16px">
          <div style="font-size:13px;color:#6b7280">桌号 {{ receiptData.tableNo }} · {{ receiptData.settledAt }}</div>
          <div style="font-size:36px;font-weight:900;color:#16a34a;margin:8px 0">¥{{ receiptData.total }}</div>
          <div style="font-size:13px;color:#6b7280">实收金额</div>
        </div>
        <div style="border-top:1px dashed #e5e7eb;margin-bottom:12px" />
        <div v-for="order in receiptData.orders" :key="order.id" style="margin-bottom:10px">
          <div v-for="item in order.items" :key="item.name + item.qty" style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
            <span style="color:#374151">{{ item.name }} × {{ item.qty }}</span>
            <span style="color:#374151;font-weight:600">¥{{ (item.price * item.qty).toFixed(2) }}</span>
          </div>
          <div v-if="order.discount_amount" style="display:flex;justify-content:space-between;font-size:12px;color:#ef4444">
            <span>优惠券抵扣</span>
            <span>-¥{{ Number(order.discount_amount).toFixed(2) }}</span>
          </div>
        </div>
        <div style="border-top:1px dashed #e5e7eb;margin:12px 0 10px" />
        <div style="display:flex;justify-content:space-between;font-size:15px;font-weight:700">
          <span>合计</span>
          <span style="color:#16a34a">¥{{ receiptData.total }}</span>
        </div>
        <a-button block style="margin-top:16px" @click="showReceiptDialog = false">关闭</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, OrderedListOutlined, EditOutlined, CheckCircleOutlined } from '@ant-design/icons-vue'
import { getOrders, updateOrderStatus, updateMerchantNote, settleTable, getReviews } from '../api'
import pollingManager from '../utils/pollingManager'

const loading = ref(false)
const orders = ref([])
const reviewsMap = ref({}) // order_id -> review
const view = ref('table')
const showSettleDialog = ref(false)
const settlingTable = ref(null)
const settling = ref(false)
const showReceiptDialog = ref(false)
const receiptData = ref(null)
const lastRefreshed = ref('')
const pollFailCount = ref(0)
const alertEnabled = ref(localStorage.getItem('orderAlertEnabled') === '1')
let prevPendingCount = null
let audioCtx = null

function _beep(ctx, freq, startOffset) {
  const gain = ctx.createGain()
  gain.connect(ctx.destination)
  const osc = ctx.createOscillator()
  osc.connect(gain)
  osc.frequency.value = freq
  gain.gain.setValueAtTime(0.4, ctx.currentTime + startOffset)
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startOffset + 0.25)
  osc.start(ctx.currentTime + startOffset)
  osc.stop(ctx.currentTime + startOffset + 0.27)
}

function playNewOrderBeep() {
  if (!alertEnabled.value || !audioCtx) return
  try {
    if (audioCtx.state === 'suspended') audioCtx.resume()
    _beep(audioCtx, 880, 0)
    _beep(audioCtx, 880, 0.3)
    _beep(audioCtx, 1100, 0.6)
  } catch {}
}

function enableAlert() {
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)()
    // 初始化播放一声确认音，同时解锁 AudioContext
    _beep(audioCtx, 880, 0)
    _beep(audioCtx, 1100, 0.25)
    alertEnabled.value = true
    localStorage.setItem('orderAlertEnabled', '1')
    message.success('接单提醒已开启，有新订单会响铃')
  } catch {
    message.error('当前浏览器不支持语音提醒')
  }
}

function disableAlert() {
  alertEnabled.value = false
  localStorage.setItem('orderAlertEnabled', '0')
  message.info('提醒已关闭')
}

async function loadOrders(pollMeta = {}) {
  loading.value = true
  try {
    const res = await getOrders({ date_str: 'today' }, { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'admin:orders:today:manage' } })
    pollFailCount.value = 0
    const raw = res?.data?.data || res?.data || []
    const uniqueOrders = Array.from(new Map((Array.isArray(raw) ? raw : []).map(o => [String(o.id), o])).values())
    const newPending = uniqueOrders.filter(o => o.status === 'pending').length
    if (prevPendingCount !== null && newPending > prevPendingCount) playNewOrderBeep()
    prevPendingCount = newPending
    orders.value = uniqueOrders.map(o => ({
      id: String(o.id),
      table: o.table_no || '-',
      diningSessionId: o.dining_session_id || null,
      status: o.status || 'pending',
      total: Number(o.total || 0),
      discount_amount: o.discount_amount ? Number(o.discount_amount) : null,
      remark: o.remark || '',
      merchant_note: o.merchant_note || '',
      merchant_note_draft: o.merchant_note || '',
      time: o.created_at ? new Date(o.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '',
      items: Array.isArray(o.items) ? o.items : [],
      updating: false,
    }))
  } catch {
    pollFailCount.value++
  }
  finally {
    loading.value = false
    const now = new Date()
    lastRefreshed.value = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
  }
}

async function loadReviews() {
  try {
    const res = await getReviews()
    const list = res?.data?.data || []
    const map = {}
    list.forEach(r => { map[r.order_id] = r })
    reviewsMap.value = map
  } catch {}
}

async function manualRefresh() {
  await loadOrders()
  message.success('已刷新', 1)
}

const pendingCount = computed(() => orders.value.filter(o => o.status === 'pending').length)
const preparingCount = computed(() => orders.value.filter(o => o.status === 'preparing').length)
const doneCount = computed(() => orders.value.filter(o => o.status === 'done').length)
const todayRevenue = computed(() =>
  orders.value.filter(o => ['preparing', 'done', 'settled'].includes(o.status)).reduce((s, o) => s + o.total, 0).toFixed(2)
)

const statItems = computed(() => [
  { label: '待接单', value: pendingCount.value, color: pendingCount.value > 0 ? '#ef4444' : '#374151' },
  { label: '备餐中', value: preparingCount.value, color: '#374151' },
  { label: '待结账', value: doneCount.value, color: '#16a34a' },
  { label: '今日营收', value: '¥' + todayRevenue.value, color: '#07C160' },
])

const statusFilter = ref('')
const statusFilters = [
  { label: '全部', val: '' },
  { label: '待接单', val: 'pending' },
  { label: '备餐中', val: 'preparing' },
  { label: '已完成', val: 'done' },
  { label: '已结账', val: 'settled' },
  { label: '已拒单', val: 'rejected' },
]

const sortedOrders = computed(() => {
  const p = { pending: 0, preparing: 1, done: 2, settled: 3, rejected: 4, cancelled: 5, pending_payment: 6 }
  const list = statusFilter.value
    ? orders.value.filter(o => o.status === statusFilter.value)
    : orders.value.filter(o => o.status !== 'pending_payment')
  return [...list].sort((a, b) => (p[a.status] ?? 9) - (p[b.status] ?? 9))
})

const tableGroups = computed(() => {
  // 按 dining_session_id 分组，而不是按桌号：同一桌当天翻台会产生多个会话，
  // 按桌号分组会把上一批已结账客人的订单和当前这批混在一起，导致结账金额和小票错乱。
  // 没有 dining_session_id 的订单（例如 H5 下单）仍按桌号分组，保持原有展示方式。
  const map = {}
  for (const o of orders.value) {
    if (['pending_payment', 'cancelled', 'rejected'].includes(o.status)) continue
    const key = o.diningSessionId ? `session:${o.diningSessionId}` : `table:${o.table}`
    if (!map[key]) map[key] = { groupKey: key, tableNo: o.table, diningSessionId: o.diningSessionId, orders: [], total: 0, updating: false }
    map[key].orders.push(o)
    map[key].total += o.total
  }
  return Object.values(map).map(t => ({
    ...t,
    pendingOrders: t.orders.filter(o => o.status === 'pending'),
    preparingOrders: t.orders.filter(o => o.status === 'preparing'),
    canSettle: t.orders.every(o => ['done', 'settled'].includes(o.status)) && t.orders.some(o => o.status === 'done'),
    isSettled: t.orders.every(o => o.status === 'settled'),
  })).sort((a, b) => {
    const p = t => t.pendingOrders.length ? 0 : t.preparingOrders.length ? 1 : t.canSettle ? 2 : 3
    return p(a) - p(b)
  })
})

function tableTagClass(t) {
  if (t.pendingOrders?.length) return 'pending'
  if (t.preparingOrders?.length) return 'preparing'
  if (t.canSettle) return 'done'
  return 'settled'
}

function tableStatusText(t) {
  if (t.pendingOrders?.length) return String(t.pendingOrders.length) + ' 单待接'
  if (t.preparingOrders?.length) return '备餐中'
  if (t.canSettle) return '可结账'
  if (t.isSettled) return '已结账'
  return ''
}

function statusLabel(s) {
  return { pending_payment: '待支付', pending: '待接单', preparing: '备餐中', done: '已完成', settled: '已结账', rejected: '已拒单', cancelled: '已取消' }[s] || s
}

async function acceptOrder(order) {
  order.updating = true
  try { await updateOrderStatus(order.id, 'preparing'); order.status = 'preparing' }
  catch { message.error('操作失败') } finally { order.updating = false }
}

async function sendMerchantNote(order) {
  if (!order.merchant_note_draft.trim()) return
  try {
    await updateMerchantNote(order.id, order.merchant_note_draft.trim())
    order.merchant_note = order.merchant_note_draft.trim()
    message.success('留言已发送，顾客查看订单时可看到')
  } catch { message.error('发送失败') }
}

async function rejectOrder(order) {
  order.updating = true
  try {
    await updateOrderStatus(order.id, 'rejected')
    order.status = 'rejected'
    message.warning('已拒单，请联系顾客说明原因')
  }
  catch { message.error('操作失败') } finally { order.updating = false }
}

async function finishOrder(order) {
  order.updating = true
  try { await updateOrderStatus(order.id, 'done'); order.status = 'done' }
  catch { message.error('操作失败') } finally { order.updating = false }
}

async function acceptTableOrders(table) {
  table.updating = true
  try {
    for (const o of table.pendingOrders) { await updateOrderStatus(o.id, 'preparing'); o.status = 'preparing' }
  } catch { message.error('操作失败') } finally { table.updating = false }
}

async function finishTableOrders(table) {
  table.updating = true
  try {
    for (const o of table.preparingOrders) { await updateOrderStatus(o.id, 'done'); o.status = 'done' }
  } catch { message.error('操作失败') } finally { table.updating = false }
}

function settleTableClick(table) { settlingTable.value = table; showSettleDialog.value = true }

async function confirmSettle() {
  if (!settlingTable.value) return
  settling.value = true
  try {
    await settleTable(settlingTable.value.tableNo)
    const table = settlingTable.value
    for (const o of table.orders) o.status = 'settled'
    showSettleDialog.value = false
    const now = new Date()
    receiptData.value = {
      tableNo: table.tableNo,
      settledAt: `${now.getFullYear()}/${now.getMonth()+1}/${now.getDate()} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`,
      total: table.total.toFixed(2),
      orders: table.orders.map(o => ({ id: o.id, items: o.items, discount_amount: o.discount_amount })),
    }
    showReceiptDialog.value = true
  } catch { message.error('结账失败，请重试') }
  finally { settling.value = false }
}


onMounted(() => {
  loadOrders()
  loadReviews()
  pollingManager.start('orders:today', {
    task: loadOrders,
    interval: 5000,
    hiddenInterval: 30000,
    idleInterval: 30000,
    immediate: false,
  })
  // 如果之前已开启提醒，静默恢复 AudioContext（等用户下次点击页面时自动解锁）
  if (alertEnabled.value) {
    try { audioCtx = new (window.AudioContext || window.webkitAudioContext)() } catch {}
  }
})
onBeforeUnmount(() => {
  pollingManager.stop('orders:today')
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 52px 16px 12px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
.page-title { font-size: 18px; font-weight: 700; color: #111; }

.alert-on-badge {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: #16a34a;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 20px;
  padding: 3px 10px;
  cursor: pointer;
  user-select: none;
}
.alert-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #16a34a;
  animation: pulse-dot 1.5s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 12px 12px 0 0;
}
.table-state { font-size: 13px; color: #6b7280; }
.table-total { font-size: 18px; font-weight: 900; color: #07C160; }

.order-row {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
}

.table-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 10px 16px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
  border-radius: 0 0 12px 12px;
}

:deep(.ant-tabs-nav) { padding: 0; }
:deep(.ant-tabs-tab) { padding: 8px 0; font-size: 14px; }

.order-action-btn {
  height: 44px !important;
  padding: 0 18px !important;
  font-size: 14px !important;
  font-weight: 700 !important;
  border-radius: 10px !important;
}
.order-action-btn--finish {
  color: #16a34a !important;
  border-color: #16a34a !important;
}
.order-action-btn--settle {
  background: #16a34a !important;
  border-color: #16a34a !important;
}
.order-action-btn--reject {
  font-weight: 700 !important;
}
.tag-rejected {
  color: #fff !important;
  background: #9ca3af !important;
  border-color: #9ca3af !important;
}
.filter-chip {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 20px;
  border: 1px solid #e5e7eb;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.filter-chip--active {
  border-color: #07C160;
  color: #07C160;
  background: #f0fdf4;
  font-weight: 600;
}

.merchant-note-row {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f0f0f0;
}
.merchant-note-input {
  flex: 1;
  height: 36px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 0 10px;
  font-size: 13px;
  outline: none;
  color: #374151;
  &:focus { border-color: #07C160; }
}
.merchant-note-send {
  height: 36px;
  padding: 0 14px;
  background: #07C160;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  &:active { opacity: .85; }
}
.review-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 6px 10px;
  background: #fffbeb;
  border-radius: 8px;
}
.review-stars-display {
  font-size: 14px;
  color: #f59e0b;
  letter-spacing: 2px;
}
.review-content-text {
  font-size: 12px;
  color: #6b7280;
  flex: 1;
}
</style>







