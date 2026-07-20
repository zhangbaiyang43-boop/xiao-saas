<template>
  <div class="custom-table">
    <div class="table-header">
      <div v-for="col in columns" :key="col.key" class="table-th" :style="{ flex: col.flex || 1 }">
        {{ col.label }}
      </div>
    </div>
    <div v-for="row in data" :key="row.id" class="table-row">
      <div v-for="col in columns" :key="col.key" class="table-td" :style="{ flex: col.flex || 1 }">
        <slot :name="col.key" :row="row">
          {{ row[col.key] }}
        </slot>
      </div>
    </div>
    <div v-if="data.length === 0" class="table-empty">
      <van-icon name="inbox-o" size="48" />
      <p>暂无数据</p>
    </div>
  </div>
</template>

<script setup>
import { Icon as VanIcon } from 'vant'

defineProps({
  columns: {
    type: Array,
    required: true
  },
  data: {
    type: Array,
    default: () => []
  }
})
</script>

<style scoped>
.custom-table {
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}

.table-header {
  display: flex;
  background: #f6f7fb;
  font-weight: 600;
}

.table-th {
  padding: 12px 16px;
  color: #6b7280;
  font-size: 13px;
}

.table-row {
  display: flex;
  border-top: 1px solid #f3f4f6;
}

.table-td {
  padding: 14px 16px;
  font-size: 14px;
  color: #111827;
}

.table-empty {
  padding: 40px;
  text-align: center;
  color: #9ca3af;
}

.table-empty p {
  margin-top: 8px;
  font-size: 14px;
}
</style>
