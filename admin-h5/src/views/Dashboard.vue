<template>
  <div class="page-wrap">
    <!-- Hero -->
    <div class="hero-header">
      <div>
        <div class="hero-date">{{ todayLabel }}</div>
        <div class="hero-name">{{ merchant.name || '我的门店' }}</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <span
          class="open-badge"
          :class="merchant.is_open !== false ? 'open-badge--on' : 'open-badge--off'"
          @click="toggleOpen"
        >{{ merchant.is_open !== false ? '营业中' : '已休息' }}</span>
        <a-button shape="circle" ghost @click="router.push('/more')" style="border-color:rgba(255,255,255,.4);color:#fff">
          <template #icon><SettingOutlined /></template>
        </a-button>
      </div>
    </div>

    <!-- 紧急提醒 -->
    <div style="padding:12px 16px 0" v-if="orderStats.pending > 0">
      <a-alert
        type="error"
        show-icon
        :message="`有 ${orderStats.pending} 单待接单，请立即处理！`"
        banner
        style="border-radius:10px;cursor:pointer;font-weight:600"
        @click="router.push('/orders')"
      >
        <template #icon><BellOutlined /></template>
      </a-alert>
    </div>


    <!-- 系统状态 -->
    <div style="padding:12px 16px 0">
      <a-card :bordered="false" class="system-status-card">
        <div class="system-status-head">
          <div>
            <div class="system-status-title">系统状态</div>
            <div class="system-status-sub">最近检测：{{ formatCheckedAt(systemStatus.checked_at) }}</div>
          </div>
          <a-button size="small" :loading="systemStatusLoading" @click="loadSystemStatus">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
        </div>
        <div class="system-status-grid">
          <div v-for="item in systemStatusItems" :key="item.key" class="system-status-item" :class="statusClass(item.status)">
            <component :is="item.status === 'ok' ? CheckCircleOutlined : ExclamationCircleOutlined" />
            <span>{{ item.label }}</span>
            <strong>{{ statusText(item.status) }}</strong>
          </div>
        </div>
        <div class="system-status-message" :class="systemHealthy ? 'system-status-message--ok' : 'system-status-message--warn'">
          {{ systemStatusError || systemStatus.message || (systemStatus.printer !== 'ok' ? '打印服务异常，请检查打印机或手动处理订单' : '系统运行正常') }}
        </div>
      </a-card>
    </div>
    <!-- 今日营收 -->
    <div style="padding:12px 16px 0">
      <a-card :bordered="false">
        <a-statistic
          title="今日营收"
          :value="orderStats.revenue"
          prefix="¥"
          :precision="2"
          :value-style="{ fontSize: '38px', fontWeight: 900, color: '#111', fontVariantNumeric: 'tabular-nums', letterSpacing: '-1px' }"
        />
        <a-divider style="margin:12px 0" />
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0">
          <div v-for="s in statItems" :key="s.label" style="text-align:center;padding:4px 0">
            <div :style="{ fontSize: '20px', fontWeight: 900, color: s.color || '#374151', fontVariantNumeric: 'tabular-nums' }">{{ s.value }}</div>
            <div style="font-size:11px;color:#9ca3af;margin-top:2px">{{ s.label }}</div>
          </div>
        </div>
      </a-card>
    </div>

    <!-- 今日数据小条 -->
    <div style="padding:8px 16px 0">
      <div style="display:flex;align-items:center;gap:16px;background:#fff;border-radius:12px;padding:10px 16px">
        <div style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-2)">
          <span style="font-weight:700;color:var(--text-1);font-variant-numeric:tabular-nums">{{ orderStats.total }}</span> 笔订单
        </div>
        <div style="width:1px;height:14px;background:var(--border)"></div>
        <div style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-2)">
          <span style="font-weight:700;color:var(--text-1);font-variant-numeric:tabular-nums">{{ stats.todayNewMembers }}</span> 位新会员
        </div>
      </div>
    </div>

    <!-- 桌台实时状态 -->
    <div style="padding:12px 16px 0">
      <a-card :bordered="false" title="桌台实时" :body-style="{ padding: tables.length ? '0' : '16px' }">
        <template #extra>
          <a-button type="link" size="small" @click="router.push('/orders')" style="padding:0;color:#07C160">查看全部</a-button>
        </template>

        <a-empty v-if="tables.length === 0" description="暂无桌台在用" :image-style="{ height: '48px' }">
          <template #image><AppstoreOutlined style="font-size:48px;color:#d1d5db" /></template>
        </a-empty>

        <a-list v-else :data-source="tables" :split="true">
          <template #renderItem="{ item }">
            <a-list-item style="padding:12px 16px;cursor:pointer" @click="router.push('/orders')">
              <a-list-item-meta>
                <template #title>
                  <span style="font-weight:600">桌号 {{ item.tableNo }}</span>
                  <a-tag :class="`tag-${item.state === 'canSettle' ? 'done' : item.state}`" size="small" style="margin-left:8px">
                    {{ tableStateLabel(item.state) }}
                  </a-tag>
                </template>
                <template #description>
                  <span style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;max-width:200px">
                    {{ item.orderCount }} 单 · {{ item.orders.map(o=>o.items?.map(i=>i.name).join('、')).join(' | ') }}
                  </span>
                </template>
              </a-list-item-meta>
              <div style="font-size:18px;font-weight:900;color:var(--text-1)">¥{{ item.total.toFixed(2) }}</div>
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </div>

    <!-- 今日爆品榜 -->
    <div v-if="topDishes.length" style="padding:12px 16px 0">
      <a-card :bordered="false" title="今日爆品榜" :body-style="{ padding: 0 }">
        <div v-for="(dish, idx) in topDishes" :key="dish.name" class="dish-rank-row">
          <div class="rank-num" :class="idx === 0 ? 'rank-1' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : ''">{{ idx + 1 }}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:14px;font-weight:600;color:var(--text-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ dish.name }}</div>
            <div style="font-size:12px;color:var(--text-2);margin-top:2px">¥{{ dish.price }} · {{ dish.category }}</div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:16px;font-weight:700;color:var(--text-1);font-variant-numeric:tabular-nums">{{ dish.qty }}</div>
            <div style="font-size:11px;color:var(--text-3)">份</div>
          </div>
        </div>
      </a-card>
    </div>

    <!-- AI 今日分析 -->
    <div style="padding:12px 16px 0">
      <a-card :bordered="false" title="✨ AI今日播报" :body-style="{ padding: '12px 16px' }">
        <div v-if="aiAnalysis" style="font-size:14px;line-height:1.8;color:#374151;white-space:pre-wrap">{{ aiAnalysis }}</div>
        <div v-else style="color:#9ca3af;font-size:13px;margin-bottom:8px">点击生成今日经营分析，AI帮你找出爆品和问题</div>
        <a-button block :loading="aiAnalyzing" @click="doAiAnalysis" style="margin-top:8px">
          {{ aiAnalysis ? '重新生成' : '生成今日分析' }}
        </a-button>
      </a-card>
    </div>

    <!-- 新商家引导 -->
    <div v-if="isNewMerchant" style="padding:12px 16px 0">
      <a-card :bordered="false" title="开店三步走">
        <a-steps direction="vertical" size="small" :current="0" :items="guideSteps" />
      </a-card>
    </div>

    <div style="height:16px" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SettingOutlined, BellOutlined, AppstoreOutlined, CheckCircleOutlined, ExclamationCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { getDashboardStats, getTenantProfile, getOrders, updateTenantSettings, getAiDailyAnalysis, getMerchantSystemStatus } from '../api'
import pollingManager from '../utils/pollingManager'

const router = useRouter()
const merchant = ref({ name: '', is_open: true })
const stats = ref({ todayNewMembers: 0 })
const orderStats = ref({ total: 0, pending: 0, preparing: 0, canSettle: 0, revenue: 0 })
const tables = ref([])
const topDishes = ref([])
const systemStatus = ref({ api: 'warning', database: 'warning', order: 'warning', payment: 'warning', printer: 'warning', checked_at: '', message: '正在检测系统状态' })
const systemStatusLoading = ref(false)
const systemStatusError = ref('')

const todayLabel = computed(() => {
  const d = new Date()
  return `${d.getMonth() + 1}月${d.getDate()}日`
})

const isNewMerchant = computed(() => orderStats.value.total === 0 && stats.value.todayNewMembers === 0)

const avgOrderValue = computed(() => {
  const paid = orderStats.value.total - orderStats.value.pending
  return paid > 0 ? (orderStats.value.revenue / paid).toFixed(1) : '0.0'
})

const statItems = computed(() => [
  { label: '待接单', value: orderStats.value.pending, color: orderStats.value.pending > 0 ? '#ef4444' : '#374151' },
  { label: '客单价', value: `¥${avgOrderValue.value}`, color: '#059952' },
  { label: '待结账', value: orderStats.value.canSettle, color: orderStats.value.canSettle > 0 ? '#d97706' : '#374151' },
])


const systemStatusItems = computed(() => [
  { key: 'api', label: '系统服务', status: systemStatus.value.api || 'warning' },
  { key: 'order', label: '订单服务', status: systemStatus.value.order || 'warning' },
  { key: 'payment', label: '支付服务', status: systemStatus.value.payment || 'warning' },
  { key: 'printer', label: '打印服务', status: systemStatus.value.printer || 'warning' },
])

const systemHealthy = computed(() => systemStatusItems.value.every(item => item.status === 'ok'))

function statusText(status) {
  return { ok: '正常', warning: '需处理', error: '异常' }[status] || '未知'
}

function statusClass(status) {
  return `system-status-item--${status || 'warning'}`
}

function formatCheckedAt(value) {
  if (!value) return '检测中'
  const date = new Date(String(value).replace(/-/g, '/'))
  if (Number.isNaN(date.getTime())) return value
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

async function loadSystemStatus() {
  systemStatusLoading.value = true
  try {
    const res = await getMerchantSystemStatus()
    if (res?.code !== 200 || !res.data) throw new Error(res?.msg || 'status unavailable')
    systemStatus.value = { ...systemStatus.value, ...res.data }
    systemStatusError.value = ''
  } catch (e) {
    systemStatusError.value = '系统状态获取失败，请稍后刷新'
  } finally {
    systemStatusLoading.value = false
  }
}
const guideSteps = [
  { title: '上菜单', description: '添加菜品，设置价格和分类' },
  { title: '生成桌码', description: '为每张桌子生成专属二维码打印贴上' },
  { title: '等待接单', description: '顾客扫码点餐后，在「接单」页处理' },
]

function tableStateLabel(s) {
  return { pending: '待接单', preparing: '备餐中', canSettle: '待结账' }[s] || s
}

async function toggleOpen() {
  const next = merchant.value.is_open === false ? true : false
  merchant.value = { ...merchant.value, is_open: next }
  try {
    await updateTenantSettings({ is_open: next })
    message.success(next ? '已开启营业' : '已切换为休息')
  } catch {
    merchant.value = { ...merchant.value, is_open: !next }
    message.error('切换失败')
  }
}

async function loadOrders(pollMeta = {}) {
  try {
    const res = await getOrders({ date_str: 'today' }, { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'admin:orders:today' } })
    const raw = res?.data?.data || res?.data || []
    if (!Array.isArray(raw)) return
    let pending = 0, preparing = 0, revenue = 0
    const tableMap = {}
    for (const o of raw) {
      const t = o.table_no || '-'
      if (!tableMap[t]) tableMap[t] = { tableNo: t, orders: [], total: 0, orderCount: 0 }
      tableMap[t].orders.push(o)
      tableMap[t].total += Number(o.total || 0)
      tableMap[t].orderCount++
      if (o.status === 'pending') pending++
      else if (o.status === 'preparing') preparing++
      if (!['pending', 'settled'].includes(o.status)) revenue += Number(o.total || 0)
    }
    orderStats.value = {
      total: raw.length, pending, preparing,
      canSettle: Object.values(tableMap).filter(t =>
        t.orders.every(o => ['done', 'settled'].includes(o.status)) && t.orders.some(o => o.status === 'done')
      ).length,
      revenue,
    }
    // 爆品统计
    const dishMap = {}
    for (const o of raw) {
      for (const item of o.items || []) {
        const k = item.name || item.dish_name || ''
        if (!k) continue
        if (!dishMap[k]) dishMap[k] = { name: k, price: item.price || 0, category: item.category || '', qty: 0 }
        dishMap[k].qty += Number(item.qty || item.quantity || 1)
      }
    }
    topDishes.value = Object.values(dishMap).sort((a, b) => b.qty - a.qty).slice(0, 5)
    tables.value = Object.values(tableMap)
      .filter(t => t.orders.some(o => o.status !== 'settled'))
      .map(t => {
        let state = 'settled'
        if (t.orders.some(o => o.status === 'pending')) state = 'pending'
        else if (t.orders.some(o => o.status === 'preparing')) state = 'preparing'
        else if (t.orders.some(o => o.status === 'done')) state = 'canSettle'
        return { ...t, state }
      })
      .sort((a, b) => ({ pending: 0, preparing: 1, canSettle: 2 }[a.state] - ({ pending: 0, preparing: 1, canSettle: 2 }[b.state])))
  } catch {}
}

const aiAnalysis = ref('')
const aiAnalyzing = ref(false)
async function doAiAnalysis() {
  aiAnalyzing.value = true
  try {
    const res = await getAiDailyAnalysis()
    if (res?.code === 200 && res.data?.analysis) {
      aiAnalysis.value = res.data.analysis
    } else {
      message.error(res?.msg || 'AI分析失败')
    }
  } catch (e) {
    message.error('AI分析失败，请稍后重试')
  } finally {
    aiAnalyzing.value = false
  }
}

onMounted(() => {
  Promise.all([
    getTenantProfile().then(r => { if (r?.code === 200) merchant.value = { name: r.data?.name || '', is_open: r.data?.is_open ?? true } }).catch(() => {}),
    getDashboardStats().then(r => { if (r?.code === 200) stats.value = { todayNewMembers: r.data?.today_new_members || 0 } }).catch(() => {}),
    loadOrders(),
    loadSystemStatus(),
  ])
  pollingManager.start('dashboard:orders:today', {
    task: loadOrders,
    interval: 30000,
    hiddenInterval: 120000,
    idleInterval: 90000,
    immediate: false,
  })
})
onBeforeUnmount(() => pollingManager.stop('dashboard:orders:today'))
</script>

<style scoped>
.open-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  &--on  { background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.4); }
  &--off { background: rgba(0,0,0,0.15); color: rgba(255,255,255,0.7); border: 1px solid rgba(255,255,255,0.2); }
}

.dish-rank-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}

.rank-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  &.rank-1 { background: #fbbf24; color: #fff; }
  &.rank-2 { background: #94a3b8; color: #fff; }
  &.rank-3 { background: #cd7c3f; color: #fff; }
}

.system-status-card :deep(.ant-card-body) {
  padding: 14px 16px;
}

.system-status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.system-status-title {
  font-size: 15px;
  font-weight: 800;
  color: var(--text-1);
}

.system-status-sub {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-3);
}

.system-status-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.system-status-item {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 9px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.system-status-item span {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-2);
}

.system-status-item strong {
  flex-shrink: 0;
  font-size: 12px;
}

.system-status-item--ok {
  background: #ecfdf5;
  color: #059669;
}

.system-status-item--warning {
  background: #fff7ed;
  color: #d97706;
}

.system-status-item--error {
  background: #fef2f2;
  color: #dc2626;
}

.system-status-message {
  margin-top: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.5;
}

.system-status-message--ok {
  background: #f0fdf4;
  color: #047857;
}

.system-status-message--warn {
  background: #fff7ed;
  color: #9a3412;
}

@media (max-width: 430px) {
  .system-status-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
:deep(.ant-steps-item-title) { font-size: 14px !important; }
:deep(.ant-steps-item-description) { font-size: 12px !important; }
:deep(.ant-card-head) { min-height: 44px; padding: 0 16px; font-size: 15px; font-weight: 600; }
:deep(.ant-card-head-title) { padding: 10px 0; }
:deep(.ant-list-item) { padding: 12px 16px !important; }
</style>



