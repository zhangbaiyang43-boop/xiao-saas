<template>
  <van-tag :type="type" round>{{ text }}</van-tag>
</template>

<script setup>
import { computed } from 'vue'
import { leadStatusText, ledgerStatusText } from '../utils/status'

const props = defineProps({
  kind: { type: String, default: 'ledger' },
  status: { type: String, default: '' },
})

const text = computed(() => props.kind === 'lead' ? leadStatusText(props.status) : ledgerStatusText(props.status))
const type = computed(() => {
  if (['AVAILABLE', 'WON'].includes(props.status)) return 'success'
  if (['PENDING', 'PROTECTED', 'CONTACTED', 'DEMO'].includes(props.status)) return 'warning'
  if (['SETTLED'].includes(props.status)) return 'primary'
  return 'default'
})
</script>
