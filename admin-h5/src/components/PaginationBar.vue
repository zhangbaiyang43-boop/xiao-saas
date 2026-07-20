<template>
  <div v-if="total > 0" class="pagination-bar">
    <span class="summary">共 {{ total }} 条</span>
    <el-pagination
      background
      :small="isCompact"
      :layout="paginationLayout"
      :current-page="page"
      :page-size="pageSize"
      :page-sizes="pageSizes"
      :total="total"
      @update:current-page="$emit('update:page', $event)"
      @update:page-size="$emit('update:pageSize', $event)"
      @size-change="$emit('change')"
      @current-change="$emit('change')"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

defineProps({
  page: {
    type: Number,
    required: true
  },
  pageSize: {
    type: Number,
    required: true
  },
  total: {
    type: Number,
    required: true
  },
  pageSizes: {
    type: Array,
    default: () => [10, 20, 50, 100]
  }
})

defineEmits(['update:page', 'update:pageSize', 'change'])

const width = ref(typeof window === 'undefined' ? 1024 : window.innerWidth)
const isCompact = computed(() => width.value < 720)
const paginationLayout = computed(() => (isCompact.value ? 'prev, pager, next' : 'sizes, prev, pager, next, jumper'))

const handleResize = () => {
  width.value = window.innerWidth
}

onMounted(() => window.addEventListener('resize', handleResize))
onUnmounted(() => window.removeEventListener('resize', handleResize))
</script>

<style scoped>
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 16px;
}

.summary {
  color: #6b7280;
  font-size: 13px;
}

@media (max-width: 720px) {
  .pagination-bar {
    align-items: stretch;
    justify-content: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
