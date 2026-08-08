<template>
  <a-drawer
    :open="open"
    placement="bottom"
    height="75%"
    :closable="false"
    :mask-closable="!submitting"
    class="pickup-sheet-drawer"
    :body-style="{ padding: '0 0 12px', maxHeight: '75vh', overflowY: 'auto' }"
    @close="onClose"
  >
    <div class="pickup-sheet">
      <div class="pickup-sheet-handle" />
      <div class="pickup-sheet-head">
        <div class="pickup-sheet-title">手里拿的是几号？</div>
        <div class="pickup-sheet-sub">看实体桌牌数字，点同一个号码</div>
      </div>

      <div v-if="loading" class="pickup-sheet-loading">号码加载中…</div>
      <div v-else class="pickup-grid">
        <button
          v-for="n in numbers"
          :key="n"
          type="button"
          class="pickup-cell"
          :class="{
            'pickup-cell--current': String(n) === String(current),
            'pickup-cell--busy': isBusy(n),
            'pickup-cell--loading': submitting && String(n) === String(pendingNo),
          }"
          :disabled="isBusy(n) || submitting"
          @click="onSelect(n)"
        >
          <span class="pickup-cell-no">{{ n }}</span>
          <span v-if="String(n) === String(current)" class="pickup-cell-tag">当前</span>
          <span v-else-if="isBusy(n)" class="pickup-cell-tag">使用中</span>
        </button>
      </div>

      <button type="button" class="pickup-sheet-cancel" :disabled="submitting" @click="onClose">取消</button>
    </div>
  </a-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  count: { type: Number, default: 30 },
  /** string[] 或 { pickup_no, dining_session_id }[] */
  occupied: { type: Array, default: () => [] },
  current: { type: [String, Number], default: '' },
  /** 当前会话 id：同会话占用不算「使用中」 */
  diningSessionId: { type: [String, Number], default: '' },
  loading: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
})

const emit = defineEmits(['update:open', 'select', 'close'])

const pendingNo = ref('')

const numbers = computed(() => {
  const total = Math.max(1, Math.min(999, Number(props.count) || 30))
  return Array.from({ length: total }, (_, i) => i + 1)
})

const occupiedSet = computed(() => {
  const set = new Set()
  for (const row of props.occupied || []) {
    if (row == null) continue
    if (typeof row === 'string' || typeof row === 'number') {
      set.add(String(row))
      continue
    }
    const sid = String(row.dining_session_id || '')
    if (props.diningSessionId && sid && sid === String(props.diningSessionId)) continue
    if (row.pickup_no != null) set.add(String(row.pickup_no))
  }
  return set
})

function isBusy(n) {
  const key = String(n)
  if (props.current && key === String(props.current)) return false
  return occupiedSet.value.has(key)
}

function onClose() {
  if (props.submitting) return
  pendingNo.value = ''
  emit('update:open', false)
  emit('close')
}

function onSelect(n) {
  if (isBusy(n) || props.submitting) return
  if (props.current && String(n) === String(props.current)) {
    onClose()
    return
  }
  pendingNo.value = String(n)
  emit('select', String(n))
}

watch(
  () => props.open,
  (v) => { if (!v) pendingNo.value = '' },
)
watch(
  () => props.submitting,
  (v) => { if (!v) pendingNo.value = '' },
)
</script>

<style scoped>
.pickup-sheet {
  padding: 8px 16px calc(12px + env(safe-area-inset-bottom));
}
.pickup-sheet-handle {
  width: 36px;
  height: 4px;
  border-radius: 999px;
  background: #e5e7eb;
  margin: 4px auto 14px;
}
.pickup-sheet-head { text-align: center; margin-bottom: 14px; }
.pickup-sheet-title {
  font-size: 18px;
  font-weight: 900;
  color: var(--text-1);
  line-height: 1.3;
}
.pickup-sheet-sub {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-3);
  line-height: 1.4;
}
.pickup-sheet-loading {
  padding: 28px 0;
  text-align: center;
  color: var(--text-3);
  font-size: 13px;
}
.pickup-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.pickup-cell {
  position: relative;
  min-height: 48px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 800;
  color: var(--text-1);
  cursor: pointer;
  padding: 0;
}
.pickup-cell:active:not(:disabled) { transform: scale(0.97); }
.pickup-cell--current {
  border-color: #16a34a;
  background: #f0fdf4;
  color: #15803d;
}
.pickup-cell--busy {
  background: #f3f4f6;
  color: #9ca3af;
  cursor: not-allowed;
}
.pickup-cell--loading { opacity: 0.7; }
.pickup-cell-no { line-height: 1; }
.pickup-cell-tag {
  position: absolute;
  right: 3px;
  bottom: 3px;
  font-size: 9px;
  font-weight: 700;
  line-height: 1;
}
.pickup-sheet-cancel {
  margin-top: 12px;
  width: 100%;
  height: 44px;
  border: none;
  border-radius: 12px;
  background: #f3f4f6;
  color: var(--text-2);
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}
@media (max-width: 360px) {
  .pickup-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
</style>
