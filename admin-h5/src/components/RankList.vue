<template>
  <a-card :bordered="false" :title="title" :body-style="{ padding: 0 }">
    <a-skeleton v-if="loading" active :title="false" :paragraph="{ rows: 3 }" style="padding:16px" />
    <div v-for="(item, idx) in items" v-else :key="item.name" class="rank-row">
      <div class="rank-num" :class="idx === 0 ? 'rank-1' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : ''">{{ idx + 1 }}</div>
      <div class="rank-main">
        <div class="rank-name">{{ item.name }}</div>
        <div v-if="item.subtitle" class="rank-subtitle">{{ item.subtitle }}</div>
      </div>
      <div class="rank-value-wrap">
        <div class="rank-value">{{ item.value }}</div>
        <div v-if="item.unit" class="rank-unit">{{ item.unit }}</div>
      </div>
    </div>
  </a-card>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  items: { type: Array, default: () => [] }, // [{ name, subtitle, value, unit }]
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.rank-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.rank-row:last-child { border-bottom: none; }

.rank-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.rank-num.rank-1 { background: var(--gold);   color: #fff; box-shadow: 0 2px 6px rgba(245,166,35,.35); }
.rank-num.rank-2 { background: var(--silver); color: #fff; box-shadow: 0 2px 6px rgba(154,165,181,.3); }
.rank-num.rank-3 { background: var(--bronze); color: #fff; box-shadow: 0 2px 6px rgba(185,113,63,.3); }

.rank-main { flex: 1; min-width: 0; }
.rank-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-subtitle { font-size: 12px; color: var(--text-2); margin-top: 2px; }

.rank-value-wrap { text-align: right; flex-shrink: 0; }
.rank-value { font-size: 16px; font-weight: 700; color: var(--text-1); font-variant-numeric: tabular-nums; }
.rank-unit { font-size: 11px; color: var(--text-3); }
</style>
