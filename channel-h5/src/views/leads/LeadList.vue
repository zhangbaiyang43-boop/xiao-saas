<template>
  <div class="list">
    <EmptyState
      v-if="!loading && items.length === 0"
      title="还没有推荐商户"
      action-text="推荐第一家商户"
      @action="$router.push('/leads/new')"
    />
    <router-link v-for="item in items" :key="item.id" class="card lead" :to="`/leads/${item.id}`">
      <div class="row">
        <div>
          <div class="item-title">{{ item.merchant_name }}</div>
          <div class="item-meta">报备 {{ formatDate(item.protected_at) }}</div>
          <div class="item-meta">保护至 {{ formatDate(item.protected_until) }}</div>
        </div>
        <StatusTag kind="lead" :status="item.status" />
      </div>
    </router-link>
    <button v-if="hasMore" class="soft-button load-more" type="button" @click="$emit('load-more')">加载更多</button>
  </div>
</template>

<script setup>
import EmptyState from '../../components/EmptyState.vue'
import StatusTag from '../../components/StatusTag.vue'
import { formatDate } from '../../utils/time'

defineEmits(['load-more'])
defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
})
</script>

<style scoped>
.lead {
  display: block;
  color: inherit;
  text-decoration: none;
}
</style>
