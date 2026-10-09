<template>
  <a-modal
    :open="open"
    :title="title"
    :footer="null"
    :mask-closable="false"
    destroy-on-close
    wrap-class-name="super-step-up-modal"
    @cancel="handleCancel"
  >
    <div class="step-up-body">
      <div class="step-up-alert">这是敏感操作。系统只记录操作原因，不会记录动态口令或密码。</div>

      <label class="step-up-label" for="step-up-reason">操作原因</label>
      <a-textarea
        id="step-up-reason"
        v-model:value="form.reason"
        :maxlength="200"
        :rows="3"
        placeholder="请填写本次操作原因"
      />

      <template v-if="allowEmergency">
        <a-checkbox v-model:checked="form.emergency" class="emergency-toggle">使用紧急暂停</a-checkbox>
      </template>

      <template v-if="!form.emergency">
        <label class="step-up-label" for="step-up-totp">动态口令</label>
        <a-input
          id="step-up-totp"
          v-model:value="form.totpCode"
          inputmode="numeric"
          maxlength="6"
          autocomplete="one-time-code"
          placeholder="认证器 App 中的 6 位动态口令"
        />
      </template>

      <template v-else>
        <div class="emergency-warning">紧急暂停仅关闭当前商户支付，不会修改或清除任何支付凭证。</div>
        <label class="step-up-label" for="step-up-password">Super Admin 密码</label>
        <a-input
          id="step-up-password"
          v-model:value="form.emergencyPassword"
          type="password"
          autocomplete="current-password"
          placeholder="输入当前管理员密码"
        />
        <label class="step-up-label" for="step-up-confirmation">紧急暂停确认短语</label>
        <div class="confirmation-copy">{{ exactConfirmation }}</div>
        <a-input
          id="step-up-confirmation"
          v-model:value="form.emergencyConfirmation"
          :placeholder="exactConfirmation"
          autocomplete="off"
        />
      </template>

      <a-checkbox v-model:checked="form.confirmed" class="confirm-check">
        我已核对商户并确认执行此操作
      </a-checkbox>

      <div class="step-up-actions">
        <a-button block @click="handleCancel">取消</a-button>
        <a-button block type="primary" danger :loading="loading" :disabled="!canSubmit" @click="submit">
          {{ confirmText }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, watch } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  confirmText?: string
  loading?: boolean
  allowEmergency?: boolean
  exactConfirmation?: string
}>(), {
  title: '安全确认',
  confirmText: '确认操作',
  loading: false,
  allowEmergency: false,
  exactConfirmation: '',
})

const emit = defineEmits<{
  cancel: []
  confirm: [payload: {
    totpCode: string
    reason: string
    confirmed: boolean
    emergency: boolean
    emergencyPassword: string
    emergencyConfirmation: string
  }]
}>()

const form = reactive({
  totpCode: '',
  reason: '',
  confirmed: false,
  emergency: false,
  emergencyPassword: '',
  emergencyConfirmation: '',
})

function clearSensitiveState(target = form) {
  Object.assign(target, {
    totpCode: '',
    reason: '',
    confirmed: false,
    emergency: false,
    emergencyPassword: '',
    emergencyConfirmation: '',
  })
}

watch(() => props.open, (open) => {
  if (!open) {
    clearSensitiveState()
    return
  }
  clearSensitiveState()
})

onBeforeUnmount(clearSensitiveState)

const canSubmit = computed(() => {
  if (!form.reason.trim() || !form.confirmed) return false
  if (!form.emergency) return /^\d{6}$/.test(form.totpCode.trim())
  return !!form.emergencyPassword && form.emergencyConfirmation === props.exactConfirmation
})

function submit() {
  if (!canSubmit.value) return
  const payload = {
    totpCode: form.totpCode.trim(),
    reason: form.reason.trim(),
    confirmed: form.confirmed,
    emergency: form.emergency,
    emergencyPassword: form.emergencyPassword,
    emergencyConfirmation: form.emergencyConfirmation,
  }
  clearSensitiveState()
  emit('confirm', payload)
}

function handleCancel() {
  clearSensitiveState()
  emit('cancel')
}
</script>

<style scoped>
.step-up-body { display: flex; flex-direction: column; gap: 12px; }
.step-up-alert, .emergency-warning { padding: 10px 12px; border-radius: 10px; background: #fff7e6; color: #8a4b08; font-size: 13px; line-height: 1.55; }
.emergency-warning { background: #fff1f0; color: #a8071a; }
.step-up-label { color: #303133; font-size: 14px; font-weight: 600; }
.emergency-toggle, .confirm-check { margin-top: 4px; }
.confirmation-copy { padding: 8px 10px; border-radius: 8px; background: #f5f5f5; color: #262626; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; word-break: break-all; }
.step-up-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px; }

@media (max-width: 390px) {
  .step-up-actions { grid-template-columns: 1fr; }
}
</style>
