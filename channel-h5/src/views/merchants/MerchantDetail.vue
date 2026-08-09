<template>
  <main class="page">
    <h1 class="page-title">成交商户</h1>
    <div v-if="loading" class="card muted">加载中...</div>
    <EmptyState
      v-else-if="error"
      title="商户记录不存在"
      description="或已无法查看"
      action-text="返回商户"
      @action="$router.push('/merchants')"
    />
    <section v-else-if="item" class="card">
      <div class="item-title">{{ item.merchant_display_name || item.tenant_id }}</div>
      <div class="item-meta">当前状态 {{ bindingStatusText(item.status) }}</div>
      <div class="item-meta">成交/绑定时间 {{ formatDateTime(item.created_at) || '已绑定' }}</div>
      <div class="item-meta">分润比例 20%</div>
      <div class="item-meta">最长期限 36个月</div>
      <div class="item-meta">分润开始 {{ item.commission_started_at ? formatDateTime(item.commission_started_at) : '等待首次有效付款' }}</div>
      <div class="item-meta">分润截止 {{ item.commission_ends_at ? formatDateTime(item.commission_ends_at) : '等待首次有效付款' }}</div>
      <div :class="merchantEarningClass(item.net_earned_cents)">
        {{ merchantNetEarnedText(item.net_earned_cents) }}
      </div>
    </section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '../../components/EmptyState.vue'
import { getMerchant } from '../../api/merchants'
import { merchantNetEarnedText } from '../../utils/money'
import { bindingStatusText } from '../../utils/status'
import { formatDateTime } from '../../utils/time'

const route = useRoute()
const item = ref(null)
const loading = ref(true)
const error = ref(false)

function merchantEarningClass(cents) {
  const value = Number(cents || 0)
  return {
    'earning-line': true,
    positive: value > 0,
    negative: value < 0,
  }
}

onMounted(async () => {
  try {
    const res = await getMerchant(route.params.id)
    if (res.code === 200) {
      item.value = res.data
    } else {
      error.value = true
    }
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.earning-line {
  margin-top: 12px;
  font-size: 15px;
  font-weight: 760;
  color: #64748b;
}
.earning-line.positive {
  color: #16a34a;
}
.earning-line.negative {
  color: #ef4444;
}
</style>
