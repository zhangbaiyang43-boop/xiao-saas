<template>
  <a-card :bordered="false" :title="title">
    <a-skeleton v-if="loading" active :title="false" :paragraph="{ rows: 3 }" />
    <div v-else-if="!points.length" class="trend-empty">暂无数据</div>
    <div v-else class="trend-chart">
      <div class="trend-bars">
        <div v-for="p in points" :key="p.date" class="trend-bar-col">
          <div class="trend-bar-value">{{ p.value > 0 ? formatValue(p.value) : '' }}</div>
          <div class="trend-bar-track">
            <div
              class="trend-bar-fill"
              :class="{ 'trend-bar-fill--today': p.isToday }"
              :style="{ height: barHeight(p.value) + '%' }"
            />
          </div>
          <div class="trend-bar-label" :class="{ 'trend-bar-label--today': p.isToday }">{{ p.label }}</div>
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup>
import { computed } from 'vue'
import { formatBeijingDate } from '../utils/beijingTime'

const props = defineProps({
  title: { type: String, default: '' },
  // [{ date: 'YYYY-MM-DD', value: number }]
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  valuePrefix: { type: String, default: '¥' },
})

const todayIso = formatBeijingDate(new Date())

const points = computed(() => props.data.map(d => {
  const dt = new Date(d.date + 'T00:00:00')
  return {
    date: d.date,
    value: Number(d.value || 0),
    isToday: d.date === todayIso,
    label: Number.isNaN(dt.getTime()) ? d.date : `${dt.getMonth() + 1}/${dt.getDate()}`,
  }
}))

const maxValue = computed(() => Math.max(...points.value.map(p => p.value), 1))

function barHeight(value) {
  if (value <= 0) return 3 // 留一点点高度，避免 0 值那天完全看不见柱子在哪
  return Math.max(6, Math.round((value / maxValue.value) * 100))
}

function formatValue(v) {
  return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : Math.round(v).toString()
}
</script>

<style scoped>
.trend-chart { padding: 4px 4px 0; }
.trend-empty { padding: 24px 0; text-align: center; color: var(--text-3); font-size: 13px; }

.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 120px;
}
.trend-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}
.trend-bar-value {
  font-size: 10px;
  color: var(--text-3);
  height: 14px;
  font-variant-numeric: tabular-nums;
}
.trend-bar-track {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.trend-bar-fill {
  width: 60%;
  min-width: 8px;
  border-radius: 4px 4px 0 0;
  background: var(--brand-light);
  transition: height .25s ease;
}
.trend-bar-fill--today {
  background: var(--brand);
}
.trend-bar-label {
  margin-top: 6px;
  font-size: 10px;
  color: var(--text-3);
}
.trend-bar-label--today {
  color: var(--brand);
  font-weight: 700;
}
</style>
