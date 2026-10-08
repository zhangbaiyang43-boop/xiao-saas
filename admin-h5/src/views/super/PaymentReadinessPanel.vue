<template>
  <section class="readiness-panel" aria-label="收款体检">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">Merchant 360 · 收款</div>
        <h3>顾客微信收款体检</h3>
        <p>{{ merchantName }} · 只读检查，不会修改支付配置</p>
      </div>
      <a-button size="small" :loading="loading" @click="loadReadiness">重新检查</a-button>
    </div>

    <div v-if="loading && !readiness" class="panel-state">正在检查本地配置…</div>
    <div v-else-if="errorText" class="panel-state panel-state--error" role="alert">
      <strong>收款体检暂时无法加载</strong>
      <span>{{ errorText }}</span>
    </div>

    <template v-else-if="readiness">
      <div class="summary-grid">
        <section class="info-card overview-card" aria-labelledby="payment-overview-title">
          <div class="card-label" id="payment-overview-title">微信在线收款概况</div>
          <div class="status-row">
            <strong :class="['readiness-status', `readiness-status--${stateTone}`]">
              {{ stateLabel }}
            </strong>
            <span>{{ online.enabled ? '在线收款已启用' : '在线收款已关闭' }}</span>
          </div>
          <p>{{ stateDescription }}</p>
        </section>

        <section class="info-card" aria-labelledby="payment-timing-title">
          <div class="card-label" id="payment-timing-title">顾客付款时机</div>
          <strong class="business-value">{{ readiness.payment_timing?.label || '付款方式未知' }}</strong>
          <p>
            {{ readiness.payment_timing?.offline_collection_available
              ? '当前业务允许线下收款；微信在线就绪状态单独计算。'
              : '当前模式依赖线上预付，不自动假设存在线下替代路径。' }}
          </p>
        </section>

        <section class="info-card" aria-labelledby="payment-config-title">
          <div class="card-label" id="payment-config-title">微信收款配置摘要</div>
          <dl class="config-summary">
            <div><dt>收款通道</dt><dd>微信支付普通商户直连</dd></div>
            <div><dt>微信支付商户号</dt><dd>{{ online.masked_identifiers?.wx_mchid || '-' }}</dd></div>
            <div><dt>验签方式</dt><dd>{{ verifyModeLabel }}</dd></div>
            <div><dt>验证等级</dt><dd>{{ validationLevelLabel }}</dd></div>
          </dl>
        </section>
      </div>

      <section class="checklist-card" aria-labelledby="payment-checklist-title">
        <div class="checklist-heading">
          <div>
            <div class="card-label" id="payment-checklist-title">配置检查清单</div>
            <p>只显示存在性、格式和本地验证结果，不显示任何密钥内容。</p>
          </div>
          <span>{{ checklist.length }} 项</span>
        </div>
        <div class="checklist">
          <article v-for="item in checklist" :key="item.code" class="check-item">
            <div class="check-main">
              <strong>{{ item.label }}</strong>
              <span :class="['check-status', `check-status--${checkTone(item.status)}`]">
                {{ checkStatusLabel(item.status) }}
              </span>
            </div>
            <p v-if="item.status !== 'CONFIGURED' && item.status !== 'NOT_APPLICABLE'">
              {{ item.remediation }}
            </p>
          </article>
        </div>
      </section>

      <div class="legacy-disclosure">
        本页原有收款配置入口仍保留，由受限运营流程维护；本体检区只读，不录入、复制、显示或修改密钥。
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSuperPaymentReadiness } from '../../api/superPaymentReadiness'

const props = defineProps({
  superToken: { type: String, required: true },
  tenantId: { type: String, required: true },
  merchantName: { type: String, default: '' },
})
const emit = defineEmits(['auth-expired'])

const readiness = ref(null)
const loading = ref(false)
const errorText = ref('')

const online = computed(() => readiness.value?.online_payment || {})
const checklist = computed(() => online.value.checklist || [])
const stateLabels = {
  DISABLED: '未启用',
  INCOMPLETE: '配置不完整',
  INVALID: '配置异常',
  UNKNOWN: '尚未完成实时验证',
  READY: '已验证可收款',
}
const stateDescriptions = {
  DISABLED: '微信在线收款当前关闭。线下付款是否可用，请以顾客付款时机为准。',
  INCOMPLETE: '当前支付路径缺少必要配置，请按检查清单补齐。',
  INVALID: '已配置内容存在可确定的格式或安全校验异常。',
  UNKNOWN: '本地配置检查已完成，但没有与当前配置绑定的可信微信实时验证证据。',
  READY: '当前配置已取得可信微信侧验证证据。',
}
const stateLabel = computed(() => stateLabels[online.value.readiness_state] || '状态未知')
const stateDescription = computed(() => stateDescriptions[online.value.readiness_state] || '暂时无法确认在线收款状态。')
const stateTone = computed(() => ({
  DISABLED: 'muted',
  INCOMPLETE: 'warning',
  INVALID: 'danger',
  UNKNOWN: 'info',
  READY: 'success',
}[online.value.readiness_state] || 'muted'))
const verifyModeLabel = computed(() => ({
  public_key: '微信支付公钥',
  platform_certificate: '微信支付平台证书',
  invalid: '配置组合异常',
}[online.value.effective_verify_mode] || '不适用'))
const validationLevelLabel = computed(() => ({
  CONFIG_PRESENT: '配置存在性检查',
  STATIC_VALID: '本地静态验证通过',
  LIVE_VERIFIED: '微信实时验证通过',
}[online.value.validation_level] || '尚未确认'))

function checkStatusLabel(status) {
  return {
    CONFIGURED: '已配置',
    MISSING: '缺失',
    INVALID: '格式异常',
    UNKNOWN: '未能确认',
    NOT_APPLICABLE: '不适用',
  }[status] || '未能确认'
}

function checkTone(status) {
  return {
    CONFIGURED: 'success',
    MISSING: 'warning',
    INVALID: 'danger',
    UNKNOWN: 'info',
    NOT_APPLICABLE: 'muted',
  }[status] || 'muted'
}

async function loadReadiness() {
  loading.value = true
  errorText.value = ''
  try {
    const response = await getSuperPaymentReadiness(props.superToken, props.tenantId)
    if (response.data?.code !== 200 || !response.data?.data) {
      errorText.value = response.data?.msg || '收款体检加载失败，请稍后重试'
      return
    }
    readiness.value = response.data.data
  } catch (error) {
    if (error?.response?.status === 401) {
      emit('auth-expired')
      return
    }
    errorText.value = error?.response?.status === 403
      ? '当前账号无权查看收款体检'
      : '网络异常，未能确认当前收款配置'
  } finally {
    loading.value = false
  }
}

onMounted(loadReadiness)
</script>

<style scoped>
.readiness-panel { display: grid; gap: 12px; margin-top: 12px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-card); background: var(--bg-card); }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.panel-kicker, .card-label { color: var(--text-3); font-size: 11px; font-weight: 800; letter-spacing: .03em; }
.panel-heading h3 { margin: 3px 0 0; color: var(--text-1); font-size: 16px; }
.panel-heading p, .info-card p, .checklist-heading p, .check-item p { margin: 4px 0 0; color: var(--text-2); font-size: 12px; line-height: 1.55; }
.panel-state { padding: 18px; border-radius: 10px; background: var(--bg-page); color: var(--text-2); text-align: center; }
.panel-state--error { display: grid; gap: 4px; background: #fef2f2; color: var(--danger); }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.info-card, .checklist-card { padding: 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-page); }
.overview-card { background: var(--bg-card); }
.status-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.status-row > span { color: var(--text-2); font-size: 12px; }
.readiness-status, .check-status { display: inline-flex; align-items: center; border-radius: 999px; font-size: 11px; font-weight: 800; }
.readiness-status { padding: 5px 9px; }
.readiness-status--success, .check-status--success { background: var(--brand-light); color: var(--success); }
.readiness-status--warning, .check-status--warning { background: #fef9c3; color: #92400e; }
.readiness-status--danger, .check-status--danger { background: #fef2f2; color: var(--danger); }
.readiness-status--info, .check-status--info { background: #eff6ff; color: #2563eb; }
.readiness-status--muted, .check-status--muted { background: #f3f4f6; color: var(--text-2); }
.business-value { display: block; margin-top: 8px; color: var(--text-1); font-size: 15px; }
.config-summary { display: grid; gap: 7px; margin: 8px 0 0; }
.config-summary div { display: flex; justify-content: space-between; gap: 12px; }
.config-summary dt { color: var(--text-3); font-size: 12px; }
.config-summary dd { margin: 0; color: var(--text-1); font-size: 12px; font-weight: 700; text-align: right; word-break: break-all; }
.checklist-card { background: var(--bg-card); }
.checklist-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.checklist-heading > span { color: var(--text-3); font-size: 11px; }
.checklist { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.check-item { padding: 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-page); }
.check-main { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.check-main strong { color: var(--text-1); font-size: 12px; }
.check-status { flex: none; padding: 3px 7px; }
.legacy-disclosure { padding: 10px 12px; border-radius: 8px; background: #fff7ed; color: #9a3412; font-size: 12px; line-height: 1.55; }
@media (max-width: 640px) {
  .summary-grid, .checklist { grid-template-columns: 1fr; }
  .panel-heading { align-items: center; }
}
</style>
