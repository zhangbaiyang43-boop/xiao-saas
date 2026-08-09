<template>
  <div class="card commission" :class="{ featured }">
    <div>
      <div class="item-title">{{ merchantName }}</div>
      <div class="item-meta">{{ entryTypeText(item.entry_type) }}</div>
      <div v-if="item.available_at && item.status === 'PENDING'" class="item-meta">{{ formatMonthDay(item.available_at) }} 后可结算</div>
      <div v-else class="item-meta">{{ formatShortDate(item.earned_at) }}</div>
    </div>
    <div class="right">
      <div :class="item.entry_type === 'REVERSAL' ? 'negative amount' : 'positive amount'">{{ signedLedgerAmount(item) }}</div>
      <StatusTag :status="item.status" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StatusTag from './StatusTag.vue'
import { formatMonthDay, formatShortDate } from '../utils/time'
import { entryTypeText, signedLedgerAmount } from '../utils/status'

const props = defineProps({
  item: { type: Object, required: true },
  featured: { type: Boolean, default: false },
})

const merchantName = computed(() => props.item.merchant_display_name || props.item.tenant_id || '成交商户')
</script>

<style scoped>
.commission {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.commission.featured {
  border-color: #ffd7c8;
  background: #fffaf7;
}
.commission.featured .item-title {
  font-size: 17px;
}
.right {
  min-width: 92px;
  text-align: right;
}
.amount {
  margin-bottom: 6px;
  font-size: 17px;
  font-weight: 780;
}
.featured .amount {
  font-size: 19px;
}
</style>
