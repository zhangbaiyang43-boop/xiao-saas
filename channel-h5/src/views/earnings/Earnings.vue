<template>
  <main class="page">
    <h1 class="page-title">收益</h1>
    <section class="card">
      <div class="grid-two">
        <div>
          <div class="muted">累计实际收益</div>
          <div class="money-sub"><MoneyText :amount="summary.net_earned_cents" /></div>
        </div>
        <div>
          <div class="muted">待结算</div>
          <div class="money-sub"><MoneyText :amount="summary.pending_cents" /></div>
        </div>
        <div>
          <div class="muted">可结算</div>
          <div class="money-sub"><MoneyText :amount="summary.available_cents" /></div>
        </div>
        <div>
          <div class="muted">已结算</div>
          <div class="money-sub"><MoneyText :amount="summary.settled_cents" /></div>
        </div>
      </div>
      <router-link class="settlement-link" to="/settlements">结算记录 ></router-link>
    </section>

    <section class="section">
      <div class="row section-title">
        <h2>收益明细</h2>
        <span class="muted">实际收益已扣除退款调整</span>
      </div>
      <EmptyState
        v-if="!loading && items.length === 0"
        title="暂无收益记录"
        description="商户产生符合条件的软件服务费后，会显示在这里"
      />
      <div v-else class="list">
        <CommissionItem v-for="item in items" :key="item.id" :item="item" />
      </div>
      <button v-if="hasMore" class="soft-button load-more" type="button" @click="loadMore">加载更多</button>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import CommissionItem from '../../components/CommissionItem.vue'
import EmptyState from '../../components/EmptyState.vue'
import MoneyText from '../../components/MoneyText.vue'
import { getCommissions } from '../../api/commissions'
import { getDashboard } from '../../api/dashboard'
import { getLeads } from '../../api/leads'
import { getMerchants } from '../../api/merchants'
import { buildMerchantNameMapFromBindings, enrichCommissions } from '../../utils/commissionEnrich'
import { appendPageItems } from '../../utils/pagination'

const summary = reactive({ net_earned_cents: 0, pending_cents: 0, available_cents: 0, settled_cents: 0 })
const items = ref([])
const page = ref(0)
const total = ref(0)
const loading = ref(false)
const hasMore = computed(() => items.value.length < total.value)
let merchantNameMap = {}

async function loadSummary() {
  const res = await getDashboard()
  if (res.code === 200) Object.assign(summary, res.data)
}

async function loadMore() {
  if (loading.value) return
  loading.value = true
  if (Object.keys(merchantNameMap).length === 0) {
    const [merchants, leads] = await Promise.all([
      getMerchants({ page: 1, page_size: 100 }),
      getLeads({ page: 1, page_size: 100 }),
    ])
    if (merchants.code === 200) merchantNameMap = buildMerchantNameMapFromBindings(merchants.data?.items || [], leads.data?.items || [])
  }
  const res = await getCommissions({ page: page.value + 1, page_size: 20 })
  if (res.code === 200) {
    page.value = res.data.page
    total.value = res.data.total
    items.value = appendPageItems(items.value, enrichCommissions(res.data.items, merchantNameMap))
  }
  loading.value = false
}

onMounted(() => {
  loadSummary()
  loadMore()
})
</script>

<style scoped>
.settlement-link {
  display: block;
  margin-top: 12px;
  color: #ff5a1f;
  text-decoration: none;
  font-weight: 720;
}
.section-title h2 {
  margin: 0;
  font-size: 18px;
}
.section-title .muted {
  max-width: 150px;
  text-align: right;
  font-size: 12px;
}
</style>
