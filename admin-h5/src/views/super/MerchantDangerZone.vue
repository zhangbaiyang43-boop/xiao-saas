<template>
  <div class="danger-zone">
    <div class="danger-zone-label">危险操作</div>
    <div class="danger-ops-actions">
      <button
        type="button"
        class="toggle-btn tap-shrink"
        :class="merchant.status ? 'stop' : 'resume'"
        :disabled="busy"
        @click="$emit('toggle-status')"
      >{{ statusButtonText }}</button>
      <button type="button" class="seed-btn tap-shrink" :disabled="busy" @click="$emit('seed')">{{ seeding ? '填充中...' : '填充测试数据' }}</button>
    </div>
    <div class="seed-hint">测试 / 开发辅助。没有订单的商户会先被清掉菜单、会员、入口码和优惠券模板，再写入演示数据。</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  merchant: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  statusBusy: { type: Boolean, default: false },
  seeding: { type: Boolean, default: false },
})
defineEmits(['toggle-status', 'seed'])

// Same wording as the original card (Phase 01 certified): platform account disable, not store hours.
const statusButtonText = computed(() => {
  if (props.statusBusy) return props.merchant.status ? '停用中...' : '恢复中...'
  return props.merchant.status ? '停用商户' : '恢复商户'
})
</script>

<style scoped>
.danger-zone { padding: 12px; border: 1px solid #fecaca; border-radius: var(--radius-card); background: #fff5f5; }
.danger-zone-label { font-size: 11px; font-weight: 800; letter-spacing: .04em; color: #dc2626; margin-bottom: 8px; }
.danger-ops-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.toggle-btn { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 0; cursor: pointer; font-weight: 700; }
.toggle-btn.stop { background: #fef2f2; color: var(--danger); }
.toggle-btn.resume { background: var(--brand-light); color: var(--success); }
.seed-btn { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 1px solid #fcd34d; background: #fffbeb; color: #92400e; cursor: pointer; font-weight: 700; }
.toggle-btn:disabled, .seed-btn:disabled { opacity: .55; cursor: not-allowed; }
.seed-hint { margin-top: 8px; font-size: 11px; line-height: 1.5; color: #92400e; }
</style>
