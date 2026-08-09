<template>
  <main class="page">
    <h1 class="page-title">结算详情</h1>
    <div v-if="loading" class="card muted">加载中...</div>
    <EmptyState
      v-else-if="error"
      title="结算记录不存在"
      description="或已无法查看"
      action-text="返回结算记录"
      @action="$router.push('/settlements')"
    />
    <section v-else-if="item" class="card">
      <div class="muted">总金额</div>
      <div class="money-main"><MoneyText :amount="item.amount_cents" /></div>
      <div class="item-meta">状态 {{ settlementStatusText(item.status) }}</div>
      <div class="item-meta">结算编号 {{ item.settlement_no }}</div>
      <div class="item-meta">结算时间 {{ formatDateTime(item.settled_at || item.approved_at) }}</div>
      <div class="item-meta">操作人 {{ item.operator || '平台' }}</div>
    </section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '../../components/EmptyState.vue'
import MoneyText from '../../components/MoneyText.vue'
import { getSettlement } from '../../api/settlements'
import { formatDateTime } from '../../utils/time'

const route = useRoute()
const item = ref(null)
const loading = ref(true)
const error = ref(false)

function settlementStatusText(status) {
  return ({
    CREATED: '处理中',
    APPROVED: '已结算',
    PAID: '已结算',
    FAILED: '结算失败',
  }[status] || '处理中')
}

onMounted(async () => {
  try {
    const res = await getSettlement(route.params.id)
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
