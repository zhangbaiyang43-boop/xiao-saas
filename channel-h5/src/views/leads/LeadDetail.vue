<template>
  <main class="page">
    <h1 class="page-title">报备详情</h1>
    <div v-if="loading" class="card muted">加载中...</div>
    <EmptyState
      v-else-if="error"
      title="报备记录不存在"
      description="或已无法查看"
      action-text="返回商户"
      @action="$router.push('/merchants')"
    />
    <section v-else-if="item" class="card">
      <div class="row">
        <div class="item-title">{{ item.merchant_name }}</div>
        <StatusTag kind="lead" :status="item.status" />
      </div>
      <div class="item-meta">老板手机号 {{ item.merchant_mobile }}</div>
      <div class="item-meta">联系人 {{ item.contact_name || '未填写' }}</div>
      <div class="item-meta">报备时间 {{ formatDateTime(item.protected_at) }}</div>
      <div class="item-meta">保护截止 {{ formatDateTime(item.protected_until) }}</div>
    </section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '../../components/EmptyState.vue'
import StatusTag from '../../components/StatusTag.vue'
import { getLead } from '../../api/leads'
import { formatDateTime } from '../../utils/time'

const route = useRoute()
const item = ref(null)
const loading = ref(true)
const error = ref(false)

onMounted(async () => {
  try {
    const res = await getLead(route.params.id)
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
