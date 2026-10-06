<template>
  <section class="adjust-card">
    <div class="adjust-head">
      <div>
        <div class="adjust-title">人工服务期调整</div>
        <div class="adjust-sub">仅用于赠送、补偿、试用延长等非收款操作</div>
      </div>
      <button v-if="context?.adjustable" class="primary-btn" @click="openModal">{{ actionLabel }}</button>
    </div>

    <div v-if="!context?.adjustable" class="blocked-tip">{{ blockedText }}</div>
    <div v-else-if="context?.natural_expiry_recovery" class="recovery-tip">
      {{ context.plan_name }} 已自然到期，本次操作将恢复该订阅并从提交时刻起延长。
    </div>

    <div class="history-head">
      <span>最近人工调整</span>
      <button class="text-btn" :disabled="historyLoading" @click="loadHistory">刷新</button>
    </div>
    <div v-if="historyLoading" class="muted">加载中...</div>
    <div v-else-if="historyError" class="error-text">{{ historyError }}</div>
    <div v-else-if="!history.length" class="muted">暂无人工调整记录</div>
    <div v-else class="history-list">
      <article v-for="item in history" :key="item.adjustment_id" class="history-item">
        <div class="history-top">
          <strong>{{ typeText(item.adjustment_type) }}</strong>
          <span>{{ formatDateTime(item.created_at) }}</span>
        </div>
        <div>{{ formatDateTime(item.before_expiry) }} → {{ formatDateTime(item.after_expiry) }}</div>
        <div class="history-meta">
          {{ item.operation_type === 'ADD_DAYS' ? `增加 ${item.delta_days} 天` : '指定到期日' }} · {{ item.operator_label }}
          <span v-if="item.natural_expiry_recovery" class="recovery-tag">恢复并延长</span>
        </div>
        <div class="history-reason">{{ item.reason }}<template v-if="item.note"> · {{ item.note }}</template></div>
        <div class="no-payment">操作来源：Super Admin · 未产生付款</div>
      </article>
    </div>

    <div v-if="visible" class="modal-mask" @click.self="closeModal">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-label="人工服务期调整">
        <div class="modal-title">{{ actionLabel }}</div>
        <div class="modal-context">
          <strong>{{ merchantName }}</strong>
          <span>Tenant ID：{{ tenantId }}</span>
          <span>套餐：{{ context?.plan_name }} · 状态：{{ contextStatusText }}</span>
          <span>开始：{{ formatDateTime(context?.started_at) }}</span>
          <span>到期：{{ formatDateTime(context?.expires_at) }} · 剩余 {{ context?.days_remaining ?? 0 }} 天</span>
        </div>

        <label class="field-label">调整方式</label>
        <div class="segmented">
          <button :class="{ active: form.operation_type === 'ADD_DAYS' }" @click="form.operation_type = 'ADD_DAYS'">增加天数</button>
          <button :class="{ active: form.operation_type === 'SET_EXPIRY_DATE' }" @click="form.operation_type = 'SET_EXPIRY_DATE'">指定到期日</button>
        </div>

        <template v-if="form.operation_type === 'ADD_DAYS'">
          <label class="field-label">增加天数</label>
          <div class="preset-row">
            <button v-for="days in [7, 30, 90, 365]" :key="days" :class="{ active: Number(form.days) === days }" @click="form.days = days">+{{ days }}天</button>
          </div>
          <input v-model.number="form.days" class="field-input" type="number" inputmode="numeric" min="1" max="365" placeholder="1-365" />
          <div class="field-help">超过 365 天请使用“指定到期日”，不要拆分多次提交。</div>
        </template>
        <template v-else>
          <label class="field-label">新到期时间</label>
          <input v-model="form.expires_at_local" class="field-input" type="datetime-local" />
          <div class="field-help">只能延后，不能缩短或保持不变。</div>
        </template>

        <label class="field-label">调整类型</label>
        <select v-model="form.adjustment_type" class="field-input">
          <option v-for="option in allowedTypes" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <label class="field-label">原因</label>
        <input v-model.trim="form.reason" class="field-input" maxlength="255" placeholder="必填，简要说明业务原因" />
        <label class="field-label">备注{{ noteRequired ? '（必填）' : '（选填）' }}</label>
        <textarea v-model.trim="form.note" class="field-input note-input" rows="3" placeholder="补充审批依据、工单号等证据" />

        <div v-if="preview" class="preview-box">
          <div class="preview-title">提交前确认</div>
          <div>调整前：{{ formatDateTime(preview.before_expiry) }}</div>
          <div>计算基线：{{ formatDateTime(preview.calculation_base_expiry) }}</div>
          <div class="preview-after">调整后：{{ formatDateTime(preview.after_expiry) }}</div>
          <div>变化：{{ preview.operation_type === 'ADD_DAYS' ? `+${preview.delta_days} 天` : '延后至指定时间' }}</div>
          <div v-if="preview.natural_expiry_recovery" class="preview-warning">这会恢复已自然到期的订阅。</div>
        </div>
        <div v-if="errorText" class="error-text modal-error">{{ errorText }}</div>

        <div class="modal-actions">
          <button class="secondary-btn" :disabled="busy" @click="closeModal">取消</button>
          <button v-if="!preview" class="primary-btn" :disabled="busy || !canPreview" @click="requestPreview">{{ busy ? '计算中...' : '预览结果' }}</button>
          <button v-else class="danger-btn" :disabled="busy" @click="submitCommit">{{ busy ? '提交中...' : confirmLabel }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  commitSubscriptionAdjustment,
  listSubscriptionAdjustments,
  previewSubscriptionAdjustment,
} from '../../api/superSubscriptionAdjustments'
import { formatBeijingDateTime } from '../../utils/beijingTime'

const props = defineProps({
  superToken: { type: String, required: true },
  tenantId: { type: String, required: true },
  merchantName: { type: String, default: '' },
  context: { type: Object, default: null },
})
const emit = defineEmits(['committed', 'auth-expired'])

const visible = ref(false)
const busy = ref(false)
const preview = ref(null)
const errorText = ref('')
const idempotencyKey = ref('')
const history = ref([])
const historyLoading = ref(false)
const historyError = ref('')
const form = reactive({
  operation_type: 'ADD_DAYS',
  days: 7,
  expires_at_local: '',
  adjustment_type: 'GIFT',
  reason: '',
  note: '',
})

const types = [
  ['GIFT', '赠送'], ['COMPENSATION', '服务补偿'], ['TRIAL_EXTENSION', '延长试用'],
  ['CORRECTION', '纠错延长'], ['INTERNAL_TEST', '内部测试'], ['OTHER', '其他'],
]
const allowedTypes = computed(() => types
  .filter(([value]) => value !== 'TRIAL_EXTENSION' || props.context?.stored_status === 'TRIAL')
  .map(([value, label]) => ({ value, label })))
const noteRequired = computed(() => ['COMPENSATION', 'CORRECTION', 'INTERNAL_TEST', 'OTHER'].includes(form.adjustment_type))
const actionLabel = computed(() => props.context?.natural_expiry_recovery
  ? '恢复并延长'
  : props.context?.stored_status === 'TRIAL' ? '延长试用' : '调整服务期')
const confirmLabel = computed(() => props.context?.natural_expiry_recovery ? '确认恢复并延长' : '确认提交调整')
const contextStatusText = computed(() => ({
  ACTIVE: '生效中', TRIAL: '试用中', EXPIRED: '已到期', CANCELLED: '已取消', FREE: '免费版',
}[props.context?.subscription_status] || '状态待确认'))
const canPreview = computed(() => {
  if (!form.reason.trim() || (noteRequired.value && !form.note.trim())) return false
  if (form.operation_type === 'ADD_DAYS') return Number.isInteger(Number(form.days)) && Number(form.days) >= 1 && Number(form.days) <= 365
  return !!form.expires_at_local
})
const blockedText = computed(() => ({
  SUBSCRIPTION_EXPIRED: '显式过期订阅不可通过普通调整恢复。',
  SUBSCRIPTION_CANCELLED: '已取消订阅不可调整服务期。',
  INFINITE_EXPIRY: '无限期订阅不可转换为有限到期日。',
  NO_ADJUSTABLE_SUBSCRIPTION: '当前没有可调整的订阅。',
  STALE_SUBSCRIPTION: '订阅记录已被新记录覆盖，请刷新。',
}[props.context?.error_code] || '当前服务期不可调整。'))

function typeText(value) {
  return Object.fromEntries(types)[value] || value
}
function formatDateTime(value) {
  return formatBeijingDateTime(value) || '未记录'
}
function makeUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
    const value = Math.random() * 16 | 0
    return (char === 'x' ? value : (value & 0x3) | 0x8).toString(16)
  })
}
function payload() {
  return {
    operation_type: form.operation_type,
    days: form.operation_type === 'ADD_DAYS' ? Number(form.days) : null,
    expires_at: form.operation_type === 'SET_EXPIRY_DATE' ? new Date(form.expires_at_local).toISOString() : null,
    adjustment_type: form.adjustment_type,
    reason: form.reason.trim(),
    note: form.note.trim() || null,
  }
}
function backendError(error, fallback) {
  return error?.response?.data?.msg || fallback
}
function openModal() {
  visible.value = true
  errorText.value = ''
}
function closeModal() {
  if (!busy.value) visible.value = false
}
async function requestPreview() {
  busy.value = true
  errorText.value = ''
  try {
    const response = await previewSubscriptionAdjustment(props.superToken, props.tenantId, payload())
    preview.value = response.data.data
  } catch (error) {
    if (error?.response?.status === 401) emit('auth-expired')
    errorText.value = backendError(error, '预览失败，请稍后重试')
  } finally {
    busy.value = false
  }
}
async function submitCommit() {
  if (!preview.value) return
  let warning
  if (preview.value.natural_expiry_recovery && preview.value.operation_type === 'ADD_DAYS') {
    warning = `当前服务已自然到期，本操作将从确认成功时刻起恢复并延长 ${preview.value.delta_days} 天。`
  } else if (preview.value.operation_type === 'SET_EXPIRY_DATE') {
    warning = `将服务到期日从 ${formatDateTime(preview.value.before_expiry)} 延后至 ${formatDateTime(preview.value.after_expiry)}。`
  } else {
    warning = `确认调整 ${props.merchantName} 的服务期，增加 ${preview.value.delta_days} 天？`
  }
  if (form.adjustment_type === 'INTERNAL_TEST') {
    warning = `这是内部测试调整，不代表付款续费。\n\n${warning}`
  }
  if (!window.confirm(warning)) return
  if (!idempotencyKey.value) idempotencyKey.value = makeUuid()
  busy.value = true
  errorText.value = ''
  try {
    const response = await commitSubscriptionAdjustment(props.superToken, props.tenantId, {
      ...payload(),
      expected_subscription_id: preview.value.subscription_id,
      expected_before_expiry: preview.value.before_expiry,
      idempotency_key: idempotencyKey.value,
    })
    visible.value = false
    preview.value = null
    idempotencyKey.value = ''
    await loadHistory()
    emit('committed', response.data.data)
  } catch (error) {
    if (error?.response?.status === 401) emit('auth-expired')
    const status = Number(error?.response?.status || 0)
    // A 5xx/gateway response can arrive after the DB commit succeeded. Keep
    // the same key so retry is a replay, never a second extension.
    const definiteFailureStatuses = [401, 403, 404, 409, 422]
    if (definiteFailureStatuses.includes(status)) {
      idempotencyKey.value = ''
      if (status === 409) preview.value = null
    }
    errorText.value = backendError(error, '提交结果未知，请保持页面并重试，系统会复用同一幂等键')
  } finally {
    busy.value = false
  }
}
async function loadHistory() {
  historyLoading.value = true
  historyError.value = ''
  try {
    const response = await listSubscriptionAdjustments(props.superToken, props.tenantId)
    history.value = response.data.data || []
  } catch (error) {
    if (error?.response?.status === 401) emit('auth-expired')
    historyError.value = backendError(error, '调整记录加载失败')
  } finally {
    historyLoading.value = false
  }
}

watch(() => [form.operation_type, form.days, form.expires_at_local, form.adjustment_type, form.reason, form.note], () => {
  preview.value = null
  idempotencyKey.value = ''
})
watch(() => props.tenantId, () => {
  visible.value = false
  preview.value = null
  idempotencyKey.value = ''
  history.value = []
  loadHistory()
})
onMounted(loadHistory)
</script>

<style scoped>
.adjust-card { margin-top: 18px; padding: 16px; border: 1px solid var(--border); border-radius: 14px; background: #fff; }
.adjust-head, .history-head, .history-top, .modal-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.adjust-title, .modal-title { font-size: 17px; font-weight: 800; color: var(--text-1); }
.adjust-sub, .muted, .history-meta { margin-top: 4px; color: var(--text-3); font-size: 12px; }
.primary-btn, .danger-btn, .secondary-btn { min-height: 42px; padding: 0 16px; border: 0; border-radius: 10px; font-weight: 700; }
.primary-btn { background: #ff4d26; color: #fff; }
.danger-btn { flex: 1; background: #d93025; color: #fff; }
.secondary-btn { background: #f3f4f6; color: var(--text-2); }
.blocked-tip, .recovery-tip { margin-top: 14px; padding: 11px 12px; border-radius: 10px; font-size: 13px; }
.blocked-tip { background: #f6f7f9; color: var(--text-3); }
.recovery-tip { background: #fff6e8; color: #9a4b00; }
.history-head { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border); font-weight: 700; }
.text-btn { border: 0; background: transparent; color: #e34b22; }
.history-list { margin-top: 8px; display: grid; gap: 8px; }
.history-item { padding: 11px; border-radius: 10px; background: #f8f9fb; font-size: 13px; line-height: 1.6; }
.history-top span, .history-reason, .no-payment { color: var(--text-3); font-size: 12px; }
.recovery-tag { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 999px; background: #fff0e8; color: #c33c17; }
.modal-mask { position: fixed; inset: 0; z-index: 80; display: flex; align-items: flex-end; justify-content: center; padding: 12px; background: rgba(0,0,0,.45); }
.modal-panel { width: min(100%, 520px); max-height: 92vh; overflow-y: auto; padding: 20px 16px calc(16px + env(safe-area-inset-bottom)); border-radius: 18px 18px 12px 12px; background: #fff; }
.modal-context { display: flex; flex-direction: column; gap: 3px; margin: 10px 0 16px; padding: 11px; border-radius: 10px; background: #f8f9fb; font-size: 13px; }
.field-label { display: block; margin: 14px 0 7px; font-size: 13px; font-weight: 700; }
.field-input { width: 100%; min-height: 44px; padding: 10px 12px; border: 1px solid #d9dce3; border-radius: 10px; background: #fff; font-size: 15px; }
.note-input { resize: vertical; }
.segmented, .preset-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.preset-row { grid-template-columns: repeat(4, 1fr); }
.segmented button, .preset-row button { min-height: 40px; border: 1px solid #d9dce3; border-radius: 9px; background: #fff; }
.segmented button.active, .preset-row button.active { border-color: #ff4d26; background: #fff2ed; color: #d83c17; font-weight: 700; }
.field-help { margin-top: 6px; color: var(--text-3); font-size: 12px; }
.preview-box { margin-top: 16px; padding: 13px; border: 1px solid #ffd1c4; border-radius: 11px; background: #fff9f6; font-size: 13px; line-height: 1.8; }
.preview-title, .preview-after { font-weight: 800; }
.preview-warning { color: #bd2e18; font-weight: 700; }
.error-text { color: #c62828; font-size: 13px; }
.modal-error { margin-top: 12px; }
.modal-actions { margin-top: 18px; }
@media (min-width: 640px) { .modal-mask { align-items: center; } .modal-panel { border-radius: 18px; } }
</style>
