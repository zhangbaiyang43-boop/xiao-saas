<template>
  <div class="mp-panel">
    <div class="section">
      <div class="section-title title-row">
        <span>待确认付款（{{ payments.length }}）</span>
        <button class="refresh-btn tap-shrink" :disabled="loading" @click="loadPayments">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>

      <div v-if="actionResult" class="action-result" :class="actionResult.ok ? 'ok' : 'err'">{{ actionResult.msg }}</div>

      <div v-if="loading && !payments.length" class="loading">加载中...</div>
      <div v-else-if="loadError" class="empty error-state">
        <div>{{ loadError }}</div>
        <button class="refresh-btn tap-shrink" @click="loadPayments">重新加载</button>
      </div>
      <div v-else-if="!payments.length" class="empty">暂无待确认付款</div>
      <div v-else class="payment-list">
        <div v-for="item in payments" :key="item.payment_id" class="payment-card">
          <div class="pc-name">{{ item.tenant_name || '未知商户' }}</div>
          <div class="pc-plan">{{ planPeriodText(item) }}</div>
          <div class="pc-amount">{{ amountText(item) }}</div>

          <div class="pc-field">
            <span class="pc-field-label">账单号</span>
            <span class="pc-field-value">{{ item.out_trade_no }}</span>
            <button class="copy-btn tap-shrink" @click="copyOutTradeNo(item)">复制</button>
          </div>

          <div class="pc-time">商家已提交 {{ relativeTime(item.manual_claimed_at) }}</div>

          <div class="pc-actions">
            <button
              class="reject-btn tap-shrink"
              :disabled="isBusy(item)"
              @click="handleRejectClick(item)"
            >{{ rejectingId === item.payment_id ? '提交中...' : '未查到到账' }}</button>
            <button
              class="confirm-btn tap-shrink"
              :disabled="isBusy(item)"
              @click="handleConfirmClick(item)"
            >{{ confirmingId === item.payment_id ? '确认中...' : '确认到账' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { confirmManualPayment, listManualPayments, rejectManualPayment } from '../../api/superBilling'
import { formatYuan, planDisplayName } from '../../utils/subscriptionUi'

const props = defineProps({
  superToken: { type: String, required: true },
})
const emit = defineEmits(['update:count'])

const payments = ref([])
const loading = ref(false)
const loadError = ref('')
const confirmingId = ref('')
const rejectingId = ref('')
const actionResult = ref(null)

function isBusy(item) {
  return confirmingId.value === item.payment_id || rejectingId.value === item.payment_id
}

function periodText(billingPeriod) {
  return billingPeriod === 'YEAR' ? '年付' : '月付'
}

function planPeriodText(item) {
  return `${planDisplayName(item.plan_code)} · ${periodText(item.billing_period)}`
}

function amountText(item) {
  return formatYuan(item.amount_cents)
}

// Backend _iso()（billing_service.py）返回的是 datetime.isoformat()，没有
// 'Z'/时区后缀，但内部一律是 datetime.utcnow() 的裸 UTC 值——new Date() 对
// 不带时区的字符串会按 JS 规范当作本地时间解析，导致相对时间整体偏移一个
// 本地 UTC 偏移量（例如"刚提交"被算成"8小时前"）。这里显式按 UTC 解析。
function parseServerUtcDate(isoString) {
  if (!isoString) return null
  const hasTimezone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(isoString)
  const date = new Date(hasTimezone ? isoString : `${isoString}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

// 相对时间为主，方便一眼判断是不是刚提交；超过 1 天改用绝对日期，避免
// "35 小时前" 这类不直观的大数字（Phase F1G-CM-C §19）。
function relativeTime(isoString) {
  const date = parseServerUtcDate(isoString)
  if (!date) return '-'
  const diffMs = Date.now() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}小时前`
  const pad = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function copyOutTradeNo(item) {
  const text = item.out_trade_no
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    actionResult.value = { ok: true, msg: '已复制账单号' }
  } catch {
    // 复制失败不影响核账流程，静默即可。
  }
}

async function loadPayments() {
  if (!props.superToken) {
    loadError.value = '请先登录平台中控台'
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const res = await listManualPayments(props.superToken)
    if (res.data?.code === 200) {
      payments.value = res.data.data || []
      emit('update:count', payments.value.length)
    } else {
      loadError.value = res.data?.msg || '待确认付款加载失败'
    }
  } catch (e) {
    loadError.value = e?.response?.data?.msg || '待确认付款加载失败，请重试'
  } finally {
    loading.value = false
  }
}

// 二次确认弹窗必须让操作者一眼核对店铺/套餐/金额/账单号——这是真实资金
// 判断，不是可撤销的表单提交（Phase F1G-CM-C §6）。
function handleConfirmClick(item) {
  const ok = window.confirm(
    `确认已到账？\n\n请确认已经在实际收款账户中看到这笔款项。\n\n${item.tenant_name || '未知商户'}\n${planPeriodText(item)}\n${amountText(item)}\n\n账单号：${item.out_trade_no}`,
  )
  if (!ok) return
  doConfirm(item)
}

function handleRejectClick(item) {
  const ok = window.confirm(
    `暂未查到到账？\n\n提交后商户将看到"暂未查到对应款项"，可再次提交付款确认。\n\n${item.tenant_name || '未知商户'} · ${planPeriodText(item)}\n账单号：${item.out_trade_no}`,
  )
  if (!ok) return
  const noteInput = window.prompt('备注（可选）', '')
  const note = (noteInput || '').trim() || undefined
  doReject(item, note)
}

// 状态冲突（例如另一个 SuperAdmin 已先处理）要用一句平实的"状态已更新"
// 带过，绝不能扣上生硬的技术错误帽子——刷新列表让 Backend authority 重新
// 说话，而不是让操作者对同一条已变化的记录重试（Phase F1G-CM-C §21）。
function isStateConflict(msg) {
  return /当前状态不允许|账单已支付|不是人工核实支付|不能驳回/.test(String(msg || ''))
}

async function doConfirm(item) {
  confirmingId.value = item.payment_id
  actionResult.value = null
  try {
    const res = await confirmManualPayment(props.superToken, item.payment_id)
    if (res.data?.code === 200) {
      actionResult.value = { ok: true, msg: '已确认到账，套餐已自动开通' }
      await loadPayments()
    } else if (isStateConflict(res.data?.msg)) {
      actionResult.value = { ok: false, msg: '该付款状态已更新' }
      await loadPayments()
    } else {
      actionResult.value = { ok: false, msg: res.data?.msg || '确认失败，请重试' }
    }
  } catch (e) {
    actionResult.value = { ok: false, msg: e?.response?.data?.msg || '网络错误，请重试' }
  } finally {
    confirmingId.value = ''
  }
}

async function doReject(item, note) {
  rejectingId.value = item.payment_id
  actionResult.value = null
  try {
    const res = await rejectManualPayment(props.superToken, item.payment_id, note)
    if (res.data?.code === 200) {
      actionResult.value = { ok: true, msg: '已驳回，商户可重新提交付款确认' }
      await loadPayments()
    } else if (isStateConflict(res.data?.msg)) {
      actionResult.value = { ok: false, msg: '该付款状态已更新' }
      await loadPayments()
    } else {
      actionResult.value = { ok: false, msg: res.data?.msg || '驳回失败，请重试' }
    }
  } catch (e) {
    actionResult.value = { ok: false, msg: e?.response?.data?.msg || '网络错误，请重试' }
  } finally {
    rejectingId.value = ''
  }
}

onMounted(loadPayments)
</script>

<style scoped>
.mp-panel { display: block; }
.section { background: var(--bg-card); border-radius: var(--radius-card); margin: 0 16px 16px; padding: 16px; }
.section-title { font-size: 15px; font-weight: 800; margin-bottom: 12px; color: var(--text-1); }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.refresh-btn { border: 1px solid var(--border); border-radius: 8px; background: var(--bg-card); color: var(--text-2); cursor: pointer; padding: 5px 12px; font-size: 13px; white-space: nowrap; }
.refresh-btn:disabled { opacity: .55; cursor: not-allowed; }
.action-result { margin-bottom: 10px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.action-result.ok { background: var(--brand-light); color: var(--success); }
.action-result.err { background: #fef2f2; color: var(--danger); }
.loading, .empty { text-align: center; color: var(--text-3); padding: 24px 0; font-size: 14px; }
.error-state { display: grid; justify-items: center; gap: 10px; }

.payment-list { display: grid; gap: 10px; }
.payment-card { padding: 14px; background: var(--bg-page); border-radius: 10px; }
.pc-name { font-size: 15px; font-weight: 800; color: var(--text-1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-plan { margin-top: 2px; font-size: 12px; color: var(--text-2); }
.pc-amount { margin-top: 6px; font-size: 22px; font-weight: 900; color: var(--text-1); }
.pc-field { display: flex; align-items: center; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
.pc-field-label { flex: 0 0 auto; font-size: 12px; color: var(--text-3); }
.pc-field-value { flex: 1; min-width: 0; font-size: 12px; color: var(--text-1); word-break: break-all; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.copy-btn { flex: 0 0 auto; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-card); color: var(--text-2); cursor: pointer; padding: 3px 10px; font-size: 12px; }
.pc-time { margin-top: 8px; font-size: 12px; color: var(--text-3); }
.pc-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
.reject-btn, .confirm-btn { height: 40px; border: 0; border-radius: 8px; font-size: 13px; font-weight: 800; cursor: pointer; }
.reject-btn { background: #fef2f2; color: var(--danger); }
.confirm-btn { background: var(--brand); color: #fff; }
.reject-btn:disabled, .confirm-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
