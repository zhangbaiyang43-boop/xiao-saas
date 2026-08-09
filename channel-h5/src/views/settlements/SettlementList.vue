<template>
  <main class="page">
    <h1 class="page-title">结算记录</h1>
    <EmptyState
      v-if="!loading && items.length === 0"
      title="暂无结算记录"
      description="符合结算条件后，由平台统一结算"
    />
    <div v-else class="list">
      <router-link v-for="item in items" :key="item.id" class="card settlement" :to="`/settlements/${item.id}`">
        <div class="row">
          <div>
            <div class="item-title">{{ item.settlement_no }}</div>
            <div class="item-meta">{{ formatDateTime(item.settled_at || item.approved_at) }}</div>
          </div>
          <div class="right">
            <div class="money-sub"><MoneyText :amount="item.amount_cents" /></div>
            <van-tag round type="primary">{{ settlementStatusText(item.status) }}</van-tag>
          </div>
        </div>
      </router-link>
    </div>
    <button v-if="hasMore" class="soft-button load-more" type="button" @click="loadMore">加载更多</button>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import EmptyState from '../../components/EmptyState.vue'
import MoneyText from '../../components/MoneyText.vue'
import { getSettlements } from '../../api/settlements'
import { appendPageItems } from '../../utils/pagination'
import { formatDateTime } from '../../utils/time'

const items = ref([])
const page = ref(0)
const total = ref(0)
const loading = ref(false)
const hasMore = computed(() => items.value.length < total.value)

function settlementStatusText(status) {
  return ({
    CREATED: '处理中',
    APPROVED: '已结算',
    PAID: '已结算',
    FAILED: '结算失败',
  }[status] || '处理中')
}

async function loadMore() {
  if (loading.value) return
  loading.value = true
  const res = await getSettlements({ page: page.value + 1, page_size: 20 })
  if (res.code === 200) {
    page.value = res.data.page
    total.value = res.data.total
    items.value = appendPageItems(items.value, res.data.items)
  }
  loading.value = false
}

onMounted(loadMore)
</script>

<style scoped>
.settlement {
  display: block;
  color: inherit;
  text-decoration: none;
}
.right {
  text-align: right;
}
</style>
