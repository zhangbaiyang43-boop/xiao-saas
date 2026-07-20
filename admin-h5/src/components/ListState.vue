<template>
  <div v-if="error" class="list-state">
    <el-empty :description="error">
      <el-button type="primary" :loading="loading" @click="$emit('retry')">重新加载</el-button>
    </el-empty>
  </div>
  <div v-else-if="!loading && empty" class="list-state">
    <el-empty :description="emptyText" />
  </div>
</template>

<script setup>
defineProps({
  loading: {
    type: Boolean,
    default: false
  },
  empty: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },
  emptyText: {
    type: String,
    default: '暂无数据'
  }
})

defineEmits(['retry'])
</script>

<style scoped>
.list-state {
  padding: 20px 0;
}
</style>
