<template>
  <div class="marketing-effectiveness-page">
    <PageHeader title="营销效果" />

    <div class="page-content">
      <section class="window-card animate-in" style="animation-delay:.02s">
        <div class="window-tabs">
          <button
            v-for="item in windowOptions"
            :key="item.days"
            :class="['window-tab', 'tap-shrink', { active: days === item.days }]"
            @click="switchWindow(item.days)"
          >
            {{ item.label }}
          </button>
        </div>
        <p class="window-hint">统计窗口：近 {{ days }} 天</p>
      </section>

      <section v-if="loading" class="state-card animate-in" style="animation-delay:.06s">
        <van-loading size="24px" color="var(--brand)">正在加载营销效果</van-loading>
      </section>

      <section v-else-if="hasError" class="state-card animate-in" style="animation-delay:.06s">
        <van-empty :description="errorMsg || '加载失败'">
          <van-button type="primary" size="small" class="tap-shrink" @click="loadData">重试</van-button>
        </van-empty>
      </section>

      <template v-else>
        <section class="table-card animate-in" style="animation-delay:.08s">
          <div class="group-title">获客 / 复购</div>
          <div class="table-head">
            <span class="col-label">渠道</span>
            <span class="col-metric">发券数</span>
            <span class="col-metric">核销率</span>
            <span class="col-metric">带来GMV</span>
            <span class="col-metric">裂变人数</span>
          </div>
          <div v-for="row in acquisitionRows" :key="row.rule_type" class="table-row">
            <span class="col-label">{{ row.label }}</span>
            <span class="col-metric">{{ formatCount(row.issued_count) }}</span>
            <span class="col-metric">{{ formatRate(row.redemption_rate) }}</span>
            <span class="col-metric">{{ formatGmv(row.gmv) }}</span>
            <span class="col-metric muted">{{ formatReferral(row.referral_headcount) }}</span>
          </div>
        </section>

        <section class="table-card animate-in" style="animation-delay:.12s">
          <div class="group-title">裂变渠道</div>
          <div class="table-head">
            <span class="col-label">渠道</span>
            <span class="col-metric">指标</span>
            <span class="col-metric">效果</span>
            <span class="col-metric">带来GMV</span>
            <span class="col-metric">裂变人数</span>
          </div>
          <div v-for="row in referralRows" :key="row.rule_type" class="table-row">
            <span class="col-label">{{ row.label }}</span>
            <span class="col-metric">
              <em class="metric-caption">{{ metricIssuedLabel(row) }}</em>
              {{ formatCount(row.issued_count) }}
            </span>
            <span class="col-metric">
              <em class="metric-caption">{{ metricRateLabel(row) }}</em>
              {{ formatRate(row.redemption_rate) }}
            </span>
            <span class="col-metric">{{ formatGmv(row.gmv) }}</span>
            <span class="col-metric">{{ formatReferral(row.referral_headcount) }}</span>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Empty as VanEmpty, Loading as VanLoading, Button as VanButton } from 'vant'
import PageHeader from '../components/PageHeader.vue'
import { getMarketingEffectiveness } from '../api'

const windowOptions = [
  { label: '近7天', days: 7 },
  { label: '近30天', days: 30 },
  { label: '近90天', days: 90 },
]

const days = ref(30)
const rows = ref([])
const loading = ref(false)
const hasError = ref(false)
const errorMsg = ref('')

const acquisitionRuleTypes = new Set([
  'entry_coupon',
  'consumption_coupon',
  'new_customer_coupon',
  'recall_coupon',
  'points_reward_coupon',
])

const acquisitionRows = computed(() => rows.value.filter(row => acquisitionRuleTypes.has(row.rule_type)))
const referralRows = computed(() => rows.value.filter(row => !acquisitionRuleTypes.has(row.rule_type)))

const metricIssuedLabel = (row) => (row.metric_kind === 'commission' ? '记账笔数' : '发券数')
const metricRateLabel = (row) => (row.metric_kind === 'commission' ? '结算率' : '核销率')

const formatCount = (value) => Number(value || 0).toLocaleString('zh-CN')

const formatRate = (value) => {
  if (value === null || value === undefined) return '暂无数据'
  return `${Math.round(Number(value) * 100)}%`
}

const formatGmv = (value) => `¥${Number(value || 0).toFixed(2)}`

const formatReferral = (value) => {
  if (value === null || value === undefined) return '—'
  return formatCount(value)
}

const getApiErrorMessage = (error, fallback = '加载失败，请稍后重试') => {
  const data = error?.response?.data || error?.data
  return data?.msg || data?.message || error?.message || fallback
}

async function loadData() {
  loading.value = true
  hasError.value = false
  errorMsg.value = ''
  try {
    const res = await getMarketingEffectiveness(days.value)
    if (res?.code !== 200) throw new Error(res?.msg || '加载失败')
    rows.value = Array.isArray(res.data?.rows) ? res.data.rows : []
  } catch (error) {
    hasError.value = true
    errorMsg.value = getApiErrorMessage(error)
    rows.value = []
  } finally {
    loading.value = false
  }
}

function switchWindow(nextDays) {
  if (days.value === nextDays) return
  days.value = nextDays
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.marketing-effectiveness-page {
  min-height: 100vh;
  background: var(--bg-page);
}

.page-content {
  padding: 12px 16px 24px;
}

.window-card,
.table-card,
.state-card {
  background: var(--bg-card);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 12px;
}

.window-tabs {
  display: flex;
  gap: 8px;
}

.window-tab {
  flex: 1;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-2);
  border-radius: 999px;
  padding: 8px 0;
  font-size: 13px;
  font-weight: 700;
}

.window-tab.active {
  border-color: var(--brand);
  background: var(--brand-light);
  color: var(--brand);
}

.window-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text-3);
}

.group-title {
  font-size: 13px;
  font-weight: 800;
  color: var(--text-2);
  margin-bottom: 12px;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: 1.2fr repeat(4, 1fr);
  gap: 8px;
  align-items: center;
}

.table-head {
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-3);
}

.table-row {
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.table-row:last-child {
  border-bottom: 0;
}

.col-label {
  font-weight: 700;
  color: var(--text-1);
}

.col-metric {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}

.col-metric.muted {
  color: var(--text-3);
}

.metric-caption {
  display: block;
  font-style: normal;
  font-size: 10px;
  color: var(--text-3);
  margin-bottom: 2px;
}

.state-card {
  display: flex;
  justify-content: center;
  padding: 32px 16px;
}
</style>
