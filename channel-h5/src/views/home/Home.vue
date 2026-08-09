<template>
  <main class="page">
    <div v-if="auth.isSuspended" class="suspended-tip">当前暂停新增商户，历史收益和结算不受影响。</div>
    <section class="card hero">
      <div class="row">
        <div>
          <div class="muted">开心点单 · 渠道伙伴</div>
          <div class="label">本月实际收益</div>
        </div>
        <van-tag v-if="auth.profile?.status" round>{{ partnerStatusText(auth.profile.status) }}</van-tag>
      </div>
      <div class="money-main"><MoneyText :amount="dashboard.month_net_earned_cents" /></div>
      <div class="grid-two section">
        <div class="mini">
          <div class="muted">可结算</div>
          <div class="money-sub"><MoneyText :amount="dashboard.available_cents" /></div>
        </div>
        <div class="mini">
          <div class="muted">待结算</div>
          <div class="money-sub"><MoneyText :amount="dashboard.pending_cents" /></div>
          <div v-if="nextAvailableText" class="mini-note">{{ nextAvailableText }}</div>
        </div>
      </div>
      <div class="row total">
        <span class="muted">累计实际收益</span>
        <MoneyText :amount="dashboard.net_earned_cents" />
      </div>
    </section>

    <section class="section">
      <button class="strong-button" type="button" :disabled="auth.isSuspended" @click="goLead">
        {{ auth.isSuspended ? '当前暂停新增商户' : '推荐新商户' }}
      </button>
    </section>

    <section class="section">
      <div class="row section-title">
        <h2>最近收益</h2>
        <router-link to="/earnings">查看全部收益</router-link>
      </div>
      <div v-if="loading" class="card muted">加载中...</div>
      <EmptyState
        v-else-if="latest.length === 0"
        title="暂无收益记录"
        description="推荐商户成交后，收益会显示在这里"
        action-text="推荐第一家商户"
        @action="goLead"
      />
      <div v-else class="list">
        <CommissionItem v-for="(item, index) in latest" :key="item.id" :item="item" :featured="index === 0" />
      </div>
    </section>

    <section class="card section">
      <div class="grid-two">
        <div>
          <div class="muted">推荐商户</div>
          <div class="stat">{{ dashboard.lead_count || 0 }}</div>
        </div>
        <div>
          <div class="muted">已成交</div>
          <div class="stat">{{ dashboard.bound_tenant_count || 0 }}</div>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { showToast } from 'vant'
import { useRouter } from 'vue-router'
import CommissionItem from '../../components/CommissionItem.vue'
import EmptyState from '../../components/EmptyState.vue'
import MoneyText from '../../components/MoneyText.vue'
import { getDashboard } from '../../api/dashboard'
import { getLeads } from '../../api/leads'
import { getMerchants } from '../../api/merchants'
import { useAuthStore } from '../../stores/auth'
import { buildMerchantNameMapFromBindings, enrichCommissions } from '../../utils/commissionEnrich'
import { createDashboardPoller } from '../../utils/polling'
import { formatMonthDay } from '../../utils/time'
import { partnerStatusText, signedLedgerAmount } from '../../utils/status'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const dashboard = reactive({
  month_net_earned_cents: 0,
  net_earned_cents: 0,
  pending_cents: 0,
  available_cents: 0,
  lead_count: 0,
  bound_tenant_count: 0,
  latest_commissions: [],
})
const latest = computed(() => dashboard.latest_commissions || [])
const nextAvailableText = computed(() => {
  const pendingDates = latest.value
    .filter((item) => item.status === 'PENDING' && item.available_at)
    .map((item) => item.available_at)
    .sort()
  const nextDate = pendingDates[0]
  return nextDate ? `预计 ${formatMonthDay(nextDate)} 后可结算` : ''
})
let poller = null
let merchantNameMap = {}

function applyDashboard(data) {
  Object.assign(dashboard, data || {})
  loading.value = false
}

async function fetchDashboardData() {
  const res = await getDashboard()
  const data = res.data || {}
  if (Array.isArray(data.latest_commissions) && data.latest_commissions.length > 0) {
    const [merchants, leads] = await Promise.all([
      getMerchants({ page: 1, page_size: 100 }),
      getLeads({ page: 1, page_size: 100 }),
    ])
    if (merchants.code === 200) {
      merchantNameMap = buildMerchantNameMapFromBindings(merchants.data?.items || [], leads.data?.items || [])
      data.latest_commissions = enrichCommissions(data.latest_commissions, merchantNameMap)
    }
  }
  return data
}

function goLead() {
  if (!auth.isSuspended) router.push('/leads/new')
}

function onNewEarn(item) {
  showToast(`${item.merchant_display_name || item.tenant_id || '成交商户'} ${signedLedgerAmount(item)}`)
}

function onVisible() {
  poller?.setVisible()
}

onMounted(() => {
  poller = createDashboardPoller({
    intervalMs: 30000,
    fetchDashboard: fetchDashboardData,
    onData: applyDashboard,
    onNewEarn,
    onError: () => { loading.value = false },
  })
  document.addEventListener('visibilitychange', onVisible)
  window.addEventListener('focus', onVisible)
  poller.start()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisible)
  window.removeEventListener('focus', onVisible)
  poller?.stop()
})
</script>

<style scoped>
.hero .label {
  margin-top: 16px;
  font-weight: 700;
}
.mini {
  min-height: 86px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
}
.mini-note {
  margin-top: 6px;
  color: #ff5a1f;
  font-size: 12px;
}
.total {
  margin-top: 14px;
  font-weight: 720;
}
.section-title h2 {
  margin: 0;
  font-size: 18px;
}
.section-title a {
  color: #ff5a1f;
  text-decoration: none;
}
.stat {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 800;
}
</style>
