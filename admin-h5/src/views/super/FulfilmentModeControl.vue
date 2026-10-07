<template>
  <section class="fulfilment-control" aria-label="接单方式">
    <div class="control-heading">
      <div>
        <div class="control-title">接单方式</div>
        <div class="control-current">当前方式：<strong>{{ currentLabel }}</strong></div>
      </div>
      <span v-if="mode === MODE_PRINT_FIRST" class="recommended-tag">推荐</span>
    </div>

    <div class="mode-options">
      <button
        class="mode-option"
        :class="{ selected: mode === MODE_PRINT_FIRST }"
        :disabled="saving"
        type="button"
        @click="selectMode(MODE_PRINT_FIRST)"
      >
        <span class="option-radio" aria-hidden="true" />
        <span>
          <strong>自动接单</strong>
          <small>顾客下单后无需人工确认，系统直接进入履约流程并按当前打印规则处理。</small>
          <em>适合大多数餐饮门店</em>
        </span>
      </button>

      <button
        class="mode-option"
        :class="{ selected: mode === MODE_WORKBENCH }"
        :disabled="saving"
        type="button"
        @click="selectMode(MODE_WORKBENCH)"
      >
        <span class="option-radio" aria-hidden="true" />
        <span>
          <strong>手动接单</strong>
          <small>顾客下单后进入待接单，需要商家人工确认后开始制作。</small>
          <em>适合需要人工确认库存、产能或订单的门店</em>
        </span>
      </button>
    </div>

    <label class="reason-field">
      <span>调整原因 <b>必填</b></span>
      <textarea
        v-model="reason"
        maxlength="200"
        rows="3"
        :disabled="saving"
        placeholder="例如：门店高峰期无需人工确认订单"
      />
    </label>

    <div v-if="errorText" class="control-result error">{{ errorText }}</div>
    <div v-if="successText" class="control-result success">{{ successText }}</div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { updateSuperFulfilmentMode } from '../../api/superFulfilmentMode'

const MODE_PRINT_FIRST = 'PRINT_FIRST'
const MODE_WORKBENCH = 'WORKBENCH'

const props = defineProps({
  superToken: { type: String, required: true },
  tenantId: { type: String, required: true },
  merchantName: { type: String, default: '' },
  mode: { type: String, default: MODE_WORKBENCH },
})
const emit = defineEmits(['updated', 'auth-expired'])

const reason = ref('')
const saving = ref(false)
const errorText = ref('')
const successText = ref('')

function modeLabel(mode) {
  return mode === MODE_PRINT_FIRST ? '自动接单' : '手动接单'
}

const currentLabel = computed(() => modeLabel(props.mode))

function confirmationText(nextMode) {
  if (nextMode === MODE_PRINT_FIRST) {
    return '开启自动接单后，后续新订单无需人工点击接单，系统会按现有打印及履约规则自动处理。'
  }
  return '开启手动接单后，后续新订单将进入待接单，需要商家人工确认后开始制作。'
}

async function selectMode(nextMode) {
  errorText.value = ''
  successText.value = ''
  if (nextMode === props.mode) return
  const normalizedReason = reason.value.trim()
  if (!normalizedReason) {
    errorText.value = '请先填写调整原因'
    return
  }
  const merchant = props.merchantName || '该商户'
  const confirmation = [
    '确认修改接单方式？',
    `商户：${merchant}`,
    `当前接单方式：${currentLabel.value}`,
    `目标接单方式：${modeLabel(nextMode)}`,
    `调整原因：${normalizedReason}`,
    confirmationText(nextMode),
    '本次调整只影响后续新订单，不会修改历史订单。',
  ].join('\n\n')
  if (!window.confirm(confirmation)) return

  saving.value = true
  try {
    const res = await updateSuperFulfilmentMode(
      props.superToken,
      props.tenantId,
      nextMode,
      normalizedReason,
    )
    if (res.data?.code !== 200) {
      errorText.value = res.data?.msg || '接单方式更新失败'
      return
    }
    reason.value = ''
    successText.value = '接单方式已更新'
    emit('updated', res.data.data)
  } catch (error) {
    if (error?.response?.status === 401) {
      emit('auth-expired')
      return
    }
    errorText.value = error?.response?.data?.msg || '接单方式更新失败，请稍后重试'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.fulfilment-control { margin-top: 12px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-card); background: #fff; }
.control-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.control-title { color: var(--text-1); font-size: 15px; font-weight: 900; }
.control-current { margin-top: 3px; color: var(--text-3); font-size: 12px; }
.recommended-tag { padding: 3px 9px; border-radius: 999px; background: #ecfdf5; color: #047857; font-size: 11px; font-weight: 800; }
.mode-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.mode-option { display: flex; gap: 9px; width: 100%; padding: 13px; border: 1px solid var(--border); border-radius: 10px; background: #fff; color: var(--text-1); text-align: left; cursor: pointer; }
.mode-option.selected { border-color: var(--brand); background: var(--brand-light); }
.mode-option:disabled { cursor: wait; opacity: .65; }
.mode-option span:last-child { display: grid; gap: 4px; }
.mode-option strong { font-size: 14px; }
.mode-option small { color: var(--text-2); font-size: 12px; line-height: 1.5; }
.mode-option em { color: var(--text-3); font-size: 11px; font-style: normal; }
.option-radio { flex: 0 0 14px; width: 14px; height: 14px; margin-top: 2px; border: 2px solid #cbd5e1; border-radius: 50%; box-shadow: inset 0 0 0 3px #fff; }
.mode-option.selected .option-radio { border-color: var(--brand); background: var(--brand); }
.reason-field { display: grid; gap: 6px; margin-top: 12px; color: var(--text-2); font-size: 12px; font-weight: 700; }
.reason-field b { color: #dc2626; font-size: 11px; }
.reason-field textarea { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: #fff; color: var(--text-1); font: inherit; font-weight: 500; resize: vertical; }
.reason-field textarea:focus { border-color: var(--brand); outline: 2px solid rgba(22, 119, 255, .12); }
.control-result { margin-top: 10px; padding: 8px 10px; border-radius: 8px; font-size: 12px; }
.control-result.error { background: #fef2f2; color: #b91c1c; }
.control-result.success { background: #ecfdf5; color: #047857; }
@media (max-width: 640px) { .mode-options { grid-template-columns: 1fr; } }
</style>
