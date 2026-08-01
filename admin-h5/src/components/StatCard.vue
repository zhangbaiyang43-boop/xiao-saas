<template>
  <a-card :bordered="false">
    <a-skeleton v-if="loading" active :title="false" :paragraph="{ rows: 3 }" />

    <div v-else-if="error" class="stat-card-error">
      <span>{{ errorText }}</span>
      <a-button size="small" @click="$emit('retry')">重试</a-button>
    </div>

    <template v-else>
      <div class="stat-card-head">
        <a-statistic
          :title="title"
          :value="value"
          :prefix="prefix"
          :precision="precision"
          :value-style="{ fontSize: '38px', fontWeight: 900, color: 'var(--text-1)', fontVariantNumeric: 'tabular-nums', letterSpacing: '-1px' }"
        />
        <div class="stat-card-head-right">
          <span
            v-if="change !== null && change !== undefined"
            class="stat-card-change"
            :class="change >= 0 ? 'stat-card-change--up' : 'stat-card-change--down'"
          >{{ change >= 0 ? '↑' : '↓' }} {{ Math.abs(change).toFixed(1) }}%</span>
          <span v-if="updatedLabel" class="stat-card-updated">{{ updatedLabel }}</span>
        </div>
      </div>
      <a-divider style="margin:12px 0" />
      <div class="stat-card-row" :style="{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }">
        <div v-for="(s, idx) in items" :key="s.label" class="stat-card-item" :class="{ 'stat-card-item--divided': idx > 0 }">
          <div class="stat-card-value">{{ s.value }}</div>
          <div class="stat-card-label">{{ s.label }}</div>
        </div>
      </div>
    </template>
  </a-card>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  value: { type: [Number, String], default: 0 },
  prefix: { type: String, default: '¥' },
  precision: { type: Number, default: 2 },
  items: { type: Array, default: () => [] }, // [{ label, value }]
  loading: { type: Boolean, default: false },
  error: { type: Boolean, default: false },
  errorText: { type: String, default: '数据加载失败' },
  updatedLabel: { type: String, default: '' },
  // 环比昨天的百分比变化，null/undefined 表示昨天没有基数、不显示环比
  change: { type: Number, default: null },
})
defineEmits(['retry'])
</script>

<style scoped>
.stat-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.stat-card-head-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.stat-card-updated {
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
}
.stat-card-change {
  font-size: 12px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.stat-card-change--up { color: var(--success); background: var(--brand-light); }
.stat-card-change--down { color: #dc2626; background: #fef2f2; }
.stat-card-row {
  display: grid;
}
.stat-card-item { text-align: center; padding: 4px 0; }
.stat-card-item--divided { border-left: 1px solid var(--border); }
.stat-card-value { font-size: 20px; font-weight: 900; color: var(--text-1); font-variant-numeric: tabular-nums; }
.stat-card-label { font-size: 11px; color: var(--text-3); margin-top: 2px; }

.stat-card-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  color: var(--text-2);
  font-size: 13px;
}
</style>
