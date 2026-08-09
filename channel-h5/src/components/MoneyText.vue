<template>
  <span :class="amount < 0 ? 'negative' : positive ? 'positive' : ''">{{ formatMoney(amount) }}</span>
</template>

<script setup>
import { formatMoney } from '../utils/money'

defineProps({
  amount: { type: Number, default: 0 },
  positive: { type: Boolean, default: false },
})
</script>
