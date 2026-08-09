<template>
  <main class="page">
    <div v-if="auth.isSuspended" class="suspended-tip">当前暂停新增商户，历史收益和结算不受影响。</div>
    <van-tabs v-model:active="active">
      <van-tab title="我的报备">
        <LeadList :items="leads" :loading="leadLoading" :has-more="leadHasMore" @load-more="loadLeads" />
      </van-tab>
      <van-tab title="已成交">
        <div class="list">
          <EmptyState
            v-if="!merchantLoading && merchants.length === 0"
            title="还没有推荐商户"
            action-text="推荐第一家商户"
            @action="$router.push('/leads/new')"
          />
          <router-link v-for="item in merchants" :key="item.id" class="card merchant" :to="`/merchants/${item.id}`">
            <div class="row">
              <div class="item-title">{{ item.merchant_display_name || item.tenant_id }}</div>
              <span class="merchant-status">{{ bindingStatusText(item.status) }}</span>
            </div>
            <div :class="merchantEarningClass(item.net_earned_cents)">
              {{ merchantNetEarnedText(item.net_earned_cents) }}
            </div>
            <div class="item-meta">成交 {{ formatDate(item.created_at) || '已绑定' }}</div>
          </router-link>
          <button v-if="merchantHasMore" class="soft-button load-more" type="button" @click="loadMerchants">加载更多</button>
        </div>
      </van-tab>
    </van-tabs>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import EmptyState from '../../components/EmptyState.vue'
import LeadList from '../leads/LeadList.vue'
import { getLeads } from '../../api/leads'
import { getMerchants } from '../../api/merchants'
import { useAuthStore } from '../../stores/auth'
import { merchantNetEarnedText } from '../../utils/money'
import { appendPageItems } from '../../utils/pagination'
import { bindingStatusText } from '../../utils/status'
import { formatDate } from '../../utils/time'

const auth = useAuthStore()
const active = ref(0)
const leads = ref([])
const merchants = ref([])
const leadPage = ref(0)
const merchantPage = ref(0)
const leadTotal = ref(0)
const merchantTotal = ref(0)
const leadLoading = ref(false)
const merchantLoading = ref(false)
const leadHasMore = computed(() => leads.value.length < leadTotal.value)
const merchantHasMore = computed(() => merchants.value.length < merchantTotal.value)

function merchantEarningClass(cents) {
  const value = Number(cents || 0)
  return {
    'earning-line': true,
    positive: value > 0,
    negative: value < 0,
  }
}

async function loadLeads() {
  if (leadLoading.value) return
  leadLoading.value = true
  const res = await getLeads({ page: leadPage.value + 1, page_size: 20 })
  if (res.code === 200) {
    leadPage.value = res.data.page
    leadTotal.value = res.data.total
    leads.value = appendPageItems(leads.value, res.data.items)
  }
  leadLoading.value = false
}

async function loadMerchants() {
  if (merchantLoading.value) return
  merchantLoading.value = true
  const res = await getMerchants({ page: merchantPage.value + 1, page_size: 20 })
  if (res.code === 200) {
    merchantPage.value = res.data.page
    merchantTotal.value = res.data.total
    merchants.value = appendPageItems(merchants.value, res.data.items)
  }
  merchantLoading.value = false
}

onMounted(() => {
  loadLeads()
  loadMerchants()
})
</script>

<style scoped>
.merchant {
  display: block;
  color: inherit;
  text-decoration: none;
}
.merchant-status {
  flex: 0 0 auto;
  color: #16a34a;
  font-size: 13px;
  font-weight: 700;
}
.earning-line {
  margin-top: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #64748b;
}
.earning-line.positive {
  color: #16a34a;
}
.earning-line.negative {
  color: #ef4444;
}
</style>
