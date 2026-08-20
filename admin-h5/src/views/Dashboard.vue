<template>
  <div class="page-wrap">
    <van-pull-refresh v-model="refreshing" @refresh="onPullRefresh">
      <!-- Hero -->
      <div class="hero-header">
        <div>
          <div class="hero-date">{{ todayLabel }}</div>
          <div class="hero-name">{{ merchant.name || '我的门店' }}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <span
            class="open-badge tap-shrink"
            :class="merchant.is_open !== false ? 'open-badge--on' : 'open-badge--off'"
            role="button"
            :aria-pressed="merchant.is_open !== false"
            aria-label="切换营业状态"
            @click="toggleOpen"
          >{{ merchant.is_open !== false ? '营业中' : '已休息' }}</span>
          <a-button shape="circle" ghost aria-label="设置" @click="router.push('/more')" style="border-color:rgba(255,255,255,.4);color:#fff">
            <template #icon><SettingOutlined /></template>
          </a-button>
        </div>
      </div>

      <!-- 套餐状态条：低视觉强度，绝不能挡在订单/KPI 之前，加载失败就直接
           不渲染，不影响 Dashboard 其它任何功能（Phase F1E-B §4）。 -->
      <div v-if="subscriptionStrip" class="section-block animate-in" style="animation-delay:.01s">
        <div
          class="subscription-strip tap-shrink"
          :class="{ 'subscription-strip--urgent': subscriptionStrip.urgent }"
          @click="router.push('/subscription')"
        >
          <span>{{ subscriptionStrip.text }}</span>
          <span class="subscription-strip-cta">{{ subscriptionStrip.cta }}</span>
        </div>
      </div>

      <!-- 待办：只有需要商家处理的事才出现，全部正常时不占版面 -->
      <div class="section-block animate-in">
        <TransitionGroup tag="div" name="list-fade" style="display:flex;flex-direction:column;gap:8px;position:relative">
          <a-alert
            v-for="item in todoItems"
            :key="item.key"
            :type="item.urgent ? 'error' : 'warning'"
            show-icon
            :message="item.text"
            :description="item.subtext || undefined"
            banner
            class="tap-shrink"
            style="border-radius:10px;cursor:pointer;font-weight:600"
            @click="item.action"
          >
            <template #icon><BellOutlined /></template>
          </a-alert>
        </TransitionGroup>
      </div>

      <!-- 今日战报：结果，只看不做 -->
      <div class="section-block animate-in" style="animation-delay:.04s">
        <StatCard
          title="今日营收"
          :value="revenueDisplay"
          :items="reportItems"
          :loading="!statsLoaded"
          :error="statsError"
          error-text="数据加载失败，请检查网络"
          :updated-label="lastUpdatedLabel"
          :change="overview.revenueChangePct"
          @retry="loadStats"
        />
      </div>

      <!-- 会员极简看板：weekly 扫一眼会员体系是否在跑 -->
      <div class="section-block animate-in" style="animation-delay:.045s">
        <StatCard
          title="会员总数"
          :value="memberPulse.total"
          prefix=""
          :precision="0"
          :items="memberPulseItems"
          :loading="!statsLoaded"
        />
      </div>

      <!-- 近7天营业额趋势 -->
      <div class="section-block animate-in" style="animation-delay:.05s">
        <TrendChart title="近7天营业额" :data="overview.trend7d" :loading="!statsLoaded" />
      </div>

      <!-- 首单→二单转化率：新客愿不愿意第二次付钱，比注册数/领券数更能说明门店的真实吸引力 -->
      <div class="section-block animate-in" style="animation-delay:.06s">
        <InsightCard :icon="RiseOutlined" title="首单→二单转化率" :loading="!statsLoaded">
          <div class="second-order-desc">{{ secondOrderConversionText }}</div>
          <div class="second-order-hint">统计口径：首单满 {{ stats.secondOrderConversion?.window_days || 30 }} 天的顾客中，有多少在这个窗口内完成了第二单</div>
        </InsightCard>
      </div>

      <!-- 智能营销：算法在后台帮商家做的事，商家在这里只看结果；要调档位去详情页郑重做决定 -->
      <div class="section-block animate-in" style="animation-delay:.08s">
        <InsightCard :icon="ThunderboltOutlined" title="智能营销" to="/coupons" :loading="!marketingLoaded">
          <template v-if="!marketingEnabled">
            <div class="marketing-off-desc">自动营销已关闭，系统不会自动给新客 / 老客发券</div>
            <a-button
              block
              type="primary"
              :loading="enablingMarketing"
              class="marketing-enable-btn"
              @click.stop="enableMarketing"
            >开启自动营销</a-button>
          </template>

          <template v-else>
            <div class="marketing-tier-row">
              <span class="marketing-tier-badge"><span class="live-dot"></span>{{ currentIntensityLabel }}档运行中</span>
              <span v-if="hasEnoughData" class="marketing-aov">客单价 ¥{{ marketingPreview.aov }}</span>
            </div>
            <div class="marketing-desc">
              <template v-if="hasEnoughData && currentOutcome">
                预计本月自动发放约 <strong>{{ currentOutcome.estimated_monthly_coupons }}</strong> 张优惠券，
                成本约 <strong>¥{{ currentOutcome.estimated_cost_per_month }}</strong>
                （约占营业额 {{ (currentOutcome.estimated_cost_ratio * 100).toFixed(1) }}%）
              </template>
              <template v-else>
                正在用安全参数自动运行，积累到 5 笔订单后系统会按你的实际客单价精算
              </template>
            </div>
            <div v-if="redemptionRateLabel" class="marketing-redemption">{{ redemptionRateLabel }}</div>
          </template>
        </InsightCard>
      </div>

      <!-- 近7天热销榜 -->
      <div v-if="topDishRankItems.length || !statsLoaded" class="section-block animate-in" style="animation-delay:.12s">
        <RankList title="近7天热销榜" :items="topDishRankItems" :loading="!statsLoaded" />
      </div>

      <!-- 新商家引导：与 Activation Home（Phase 02）内容重复，改成低优先级
           入口——整卡可点，跳到完整的开店引导页 -->
      <div v-if="isNewMerchant" class="section-block animate-in tap-shrink" style="animation-delay:.16s;cursor:pointer" @click="router.push('/activation')">
        <a-card :bordered="false" title="开店三步走">
          <a-steps direction="vertical" size="small" :current="0" :items="guideSteps" />
        </a-card>
      </div>

      <div style="height:16px" />
    </van-pull-refresh>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SettingOutlined, BellOutlined, ThunderboltOutlined, RiseOutlined } from '@ant-design/icons-vue'
import { getDashboardStats, getTenantProfile, getOrders, updateTenantSettings, getMerchantSystemStatus, getMarketingPreview, getTableCouponActivity, getCurrentSubscription } from '../api'
import { homeStatusStripCopy } from '../utils/subscriptionUi'
import pollingManager from '../utils/pollingManager'
import { useCountUp } from '../composables/useCountUp'
import StatCard from '../components/StatCard.vue'
import InsightCard from '../components/InsightCard.vue'
import RankList from '../components/RankList.vue'
import TrendChart from '../components/TrendChart.vue'

const router = useRouter()
const merchant = ref({ name: '', is_open: true, is_new_merchant: false })
const stats = ref({ todayNewMembers: 0, secondOrderConversion: null })
const memberPulse = ref({ total: 0, repeat7d: 0, pointsIssued: 0, pointsRedeemed: 0 })
// pending/preparing/canSettle 是"现在这一刻要不要处理"的实时状态，跟"今天赚了多少钱"
// 是两回事，继续从当前订单列表现算；营收/订单数/客单价/环比/趋势/热销榜这些是"日结果"
// 类指标，统一交给后端按 payment_status 算，不再用前端这份订单列表自己拼营业额
// （旧逻辑按业务状态白名单/黑名单判断该不该计入营业额，取消单会被误计入，结账后的
// 单反而被漏算，是真实存在过的错误统计口径）。
const orderStats = ref({ pending: 0, preparing: 0, canSettle: 0 })
const overview = ref({
  todayOrderCount: 0, todayRevenue: 0, todayAov: 0,
  revenueChangePct: null, orderCountChangePct: null,
  trend7d: [], topDishes7d: [],
})
const statsLoaded = ref(false)
const statsError = ref(false)
const lastUpdatedAt = ref(null)
const refreshing = ref(false)
const revenueDisplay = useCountUp(computed(() => overview.value.todayRevenue))
const flaggedTables = ref([])
const subscriptionStrip = ref(null)
const systemStatus = ref({ api: 'warning', database: 'warning', order: 'warning', payment: 'warning', printer: 'warning', checked_at: '', message: '正在检测系统状态' })
const systemStatusLoading = ref(false)
const systemStatusError = ref('')

const todayLabel = computed(() => {
  const d = new Date()
  return `${d.getMonth() + 1}月${d.getDate()}日`
})

const lastUpdatedLabel = computed(() => {
  if (!lastUpdatedAt.value) return ''
  const d = lastUpdatedAt.value
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')} 已更新`
})

const isNewMerchant = computed(() => merchant.value.is_new_merchant)

// 今日战报：只看不做的结果类指标（行动类指标——待接单/待结账——在下面的待办里）
const reportItems = computed(() => [
  { label: '订单数', value: overview.value.todayOrderCount },
  { label: '客单价', value: overview.value.todayAov ? `¥${overview.value.todayAov}` : '-' },
  { label: '新会员', value: stats.value.todayNewMembers },
])

const memberPulseItems = computed(() => [
  { label: '7日回头客', value: memberPulse.value.repeat7d },
  { label: '本月积分发放', value: memberPulse.value.pointsIssued },
  { label: '本月积分核销', value: memberPulse.value.pointsRedeemed },
])

// 首单→二单转化率：新客最该被盯的一个指标——比注册数、领券数都更能说明菜品/价格/
// 门店留不留得住人。样本不够（cohort_size 为 0，通常是新店还没攒够"首单满30天"的
// 顾客）时不硬凑一个百分比出来，只提示还在积累数据。
const secondOrderConversionText = computed(() => {
  const c = stats.value.secondOrderConversion
  if (!c || !c.cohort_size) return '数据积累中，暂无足够样本'
  return `${Math.round((c.rate || 0) * 100)}%（${c.converted_count}/${c.cohort_size} 位顾客）`
})

const topDishRankItems = computed(() => overview.value.topDishes7d.map(d => ({
  name: d.name,
  value: d.qty,
  unit: '份',
})))

const systemStatusItems = computed(() => [
  { key: 'api', label: '系统服务', status: systemStatus.value.api || 'warning' },
  { key: 'order', label: '订单服务', status: systemStatus.value.order || 'warning' },
  { key: 'payment', label: '支付服务', status: systemStatus.value.payment || 'warning' },
  { key: 'printer', label: '打印服务', status: systemStatus.value.printer || 'warning' },
])

const systemHealthy = computed(() => systemStatusItems.value.every(item => item.status === 'ok'))

// 系统状态最近一次检测的时间，跟结果类信息的"已更新"角标是同一个套路。
const systemStatusCheckedLabel = computed(() => {
  if (!systemStatus.value.checked_at) return ''
  const d = new Date(systemStatus.value.checked_at)
  if (Number.isNaN(d.getTime())) return ''
  return `最近检测 ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
})

// 待办：需要商家处理的事，合并了原来分散的"紧急提醒"+"系统状态"+"待结账"，
// 没有待办时这一块完全不渲染，把版面让给下面的结果类信息（Jobs 原则：异常才说话，正常静默）。
const todoItems = computed(() => {
  const items = []
  if (orderStats.value.pending > 0) {
    items.push({ key: 'pending', urgent: true, text: `有 ${orderStats.value.pending} 单待接单，请立即处理`, action: () => router.push('/orders') })
  }
  if (orderStats.value.canSettle > 0) {
    items.push({ key: 'settle', urgent: false, text: `有 ${orderStats.value.canSettle} 桌待结账`, action: () => router.push('/orders') })
  }
  if (!systemHealthy.value) {
    const printerBad = systemStatus.value.printer && systemStatus.value.printer !== 'ok'
    items.push({
      key: 'system',
      urgent: true,
      text: systemStatusError.value || (printerBad ? '打印服务异常，请检查打印机或手动处理订单' : (systemStatus.value.message || '打印或支付服务需要处理，点击重新检测')),
      subtext: systemStatusCheckedLabel.value,
      action: () => loadSystemStatus(),
    })
  }
  // 拆单套券这类问题没有做自动拦截（容易误伤正常大桌聚餐），改成这里"异常才说话"：
  // 同一桌同一天扎堆出现好几个"首单新客"才提示，正常情况完全不出现。
  for (const t of flaggedTables.value) {
    items.push({
      key: `table-coupon-${t.dining_session_id}`,
      urgent: false,
      text: `桌 ${t.table_no || '未知'} 今天有 ${t.new_customer_count} 位新客户扎堆完成首单，建议核实是否为正常聚餐`,
      subtext: `共 ${t.order_count} 单 · ${t.customer_count} 位顾客`,
      action: () => router.push('/orders'),
    })
  }
  return items
})

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

// 静默失败：这只是个观察性提示，不是关键操作路径，加载失败就当作"今天没有异常桌"，
// 不打扰商家，下次轮询/刷新再试。
async function loadTableCouponActivity() {
  try {
    const res = await getTableCouponActivity()
    if (res?.code === 200) flaggedTables.value = (res.data?.tables || []).filter(t => t.flagged)
  } catch {
    // 静默失败
  }
}
// 静默失败：套餐状态条是次要商业曝光，绝不能因为这一个请求失败就影响
// 商家接单——失败就干脆不展示这条状态，Dashboard 其它任何功能不受影响。
async function loadSubscriptionStrip() {
  try {
    const res = await getCurrentSubscription()
    if (res?.code === 200) subscriptionStrip.value = homeStatusStripCopy(res.data)
  } catch {
    subscriptionStrip.value = null
  }
}

const guideSteps = [
  { title: '上菜单', description: '添加菜品，设置价格和分类' },
  { title: '生成桌码', description: '为每张桌子生成专属二维码打印贴上' },
  { title: '等待接单', description: '顾客扫码点餐后，在「接单」页处理' },
]

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
  const res = await getOrders({ date_str: 'today' }, { meta: { fromPolling: Boolean(pollMeta.fromPolling), dedupe: true, dedupeKey: 'admin:orders:today' } })
  const raw = res?.data?.data || res?.data || []
  if (!Array.isArray(raw)) throw new Error('订单数据格式异常')
  let pending = 0, preparing = 0
  const tableMap = {}
  for (const o of raw) {
    const t = o.table_no || '-'
    if (!tableMap[t]) tableMap[t] = { orders: [] }
    tableMap[t].orders.push(o)
    if (o.status === 'pending') pending++
    else if (o.status === 'preparing') preparing++
  }
  orderStats.value = {
    pending, preparing,
    canSettle: Object.values(tableMap).filter(t =>
      t.orders.every(o => ['done', 'settled'].includes(o.status)) && t.orders.some(o => o.status === 'done')
    ).length,
  }
}

// 今日战报的数据来源（订单概况 + 新会员数），统一管理加载态/错误态/更新时间，
// 供骨架屏、失败重试、"已更新"角标复用。
async function loadStats(pollMeta = {}) {
  try {
    await Promise.all([
      getDashboardStats().then(r => {
        if (r?.code !== 200) return
        const d = r.data || {}
        stats.value = { todayNewMembers: d.today_new_members || 0, secondOrderConversion: d.second_order_conversion || null }
        memberPulse.value = {
          total: d.customer_count || 0,
          repeat7d: d.repeat_customers_7d || 0,
          pointsIssued: d.points_issued_month || 0,
          pointsRedeemed: d.points_redeemed_coupons_month || 0,
        }
        overview.value = {
          todayOrderCount: d.today_order_count || 0,
          todayRevenue: d.today_revenue || 0,
          todayAov: d.today_aov || 0,
          revenueChangePct: d.revenue_change_pct ?? null,
          orderCountChangePct: d.order_count_change_pct ?? null,
          trend7d: d.trend_7d || [],
          topDishes7d: d.top_dishes_7d || [],
        }
      }),
      loadOrders(pollMeta),
    ])
    statsError.value = false
    lastUpdatedAt.value = new Date()
  } catch (e) {
    statsError.value = true
  } finally {
    statsLoaded.value = true
  }
}

async function onPullRefresh() {
  await Promise.all([loadStats(), loadMarketingPreview(), loadSystemStatus(), loadTableCouponActivity(), loadSubscriptionStrip()])
  refreshing.value = false
  if (!statsError.value) message.success('已刷新')
}

// 智能营销卡片
const marketingLoaded = ref(false)
const marketingPreview = ref({})
const enablingMarketing = ref(false)
const intensityLabels = { conservative: '保守', standard: '标准', aggressive: '激进' }

const marketingEnabled = computed(() => marketingPreview.value?.consumption_coupon?.enabled !== false)
const currentIntensity = computed(() => marketingPreview.value?.intensity_outcomes?.current_intensity || 'standard')
const currentIntensityLabel = computed(() => intensityLabels[currentIntensity.value] || '标准')
const hasEnoughData = computed(() => marketingPreview.value?.intensity_outcomes?.has_enough_data ?? false)
const currentOutcome = computed(() => {
  const outcomes = marketingPreview.value?.intensity_outcomes?.outcomes || []
  return outcomes.find(o => o.is_current) || null
})
// 核销率：发了多少张不重要，用了多少张才是券真正带来客单价的证据
const redemptionRateLabel = computed(() => {
  const rate = marketingPreview.value?.redemption_rate
  if (rate === null || rate === undefined) return null
  return `核销率 ${(rate * 100).toFixed(0)}%（${marketingPreview.value.redeemed_this_month ?? 0}/${marketingPreview.value.issued_this_month ?? 0}张）`
})

async function loadMarketingPreview() {
  try {
    const res = await getMarketingPreview()
    if (res?.code === 200) marketingPreview.value = res.data || {}
  } catch {
    // 静默失败：营销卡片不是关键操作路径，失败了就保持骨架屏，不打扰商家
  } finally {
    marketingLoaded.value = true
  }
}

async function enableMarketing() {
  enablingMarketing.value = true
  try {
    await updateTenantSettings({
      coupon_rules: {
        new_customer_coupon: { enabled: true },
        consumption_coupon: { enabled: true },
        recall_coupon: { enabled: true },
        entry_coupon: { enabled: true },
        points_reward_coupon: { enabled: true },
      },
    })
    await loadMarketingPreview()
    message.success('已开启自动营销')
  } catch {
    message.error('开启失败，请稍后重试')
  } finally {
    enablingMarketing.value = false
  }
}

onMounted(() => {
  getTenantProfile().then(r => {
    if (r?.code === 200) merchant.value = { name: r.data?.name || '', is_open: r.data?.is_open ?? true, is_new_merchant: Boolean(r.data?.is_new_merchant) }
  }).catch(() => {})
  loadStats()
  loadSystemStatus()
  loadMarketingPreview()
  loadTableCouponActivity()
  loadSubscriptionStrip()

  pollingManager.start('dashboard:orders:today', {
    task: (meta) => loadStats(meta).catch(() => {}),
    interval: 30000,
    hiddenInterval: 120000,
    idleInterval: 90000,
    immediate: false,
  })
})
onBeforeUnmount(() => pollingManager.stop('dashboard:orders:today'))
</script>

<style scoped>
.subscription-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-2);
  font-size: 12px;
  font-weight: 600;
}
.subscription-strip-cta { color: var(--brand); font-weight: 800; }
.subscription-strip--urgent { border-color: #fde68a; background: #fffbeb; }
.subscription-strip--urgent .subscription-strip-cta { color: #92400e; }

.open-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  &.open-badge--on  { background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.4); }
  &.open-badge--off { background: rgba(0,0,0,0.15); color: rgba(255,255,255,0.7); border: 1px solid rgba(255,255,255,0.2); }
}

.second-order-desc { font-size: 20px; font-weight: 800; color: var(--text-1); }
.second-order-hint { margin-top: 6px; font-size: 12px; color: var(--text-3); line-height: 1.5; }

.marketing-off-desc { color: var(--text-2); font-size: 13px; margin-bottom: 10px; }
.marketing-enable-btn { background: var(--brand); border-color: var(--brand); }

.marketing-tier-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.marketing-tier-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--brand-light);
  color: var(--success);
  font-size: 12px;
  font-weight: 700;
}
.marketing-aov { font-size: 12px; color: var(--text-3); }

.marketing-desc {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.6;
  margin-top: 10px;
}

.marketing-redemption {
  display: inline-block;
  margin-top: 8px;
  padding: 3px 10px;
  border-radius: 999px;
  background: #fff7e6;
  color: #9a5b13;
  font-size: 12px;
  font-weight: 700;
}

:deep(.ant-steps-item-title) { font-size: 14px !important; }
:deep(.ant-steps-item-description) { font-size: 12px !important; }
:deep(.ant-card-head) { min-height: 44px; padding: 0 16px; font-size: 15px; font-weight: 600; }
:deep(.ant-card-head-title) { padding: 10px 0; }
:deep(.ant-list-item) { padding: 12px 16px !important; }
</style>
