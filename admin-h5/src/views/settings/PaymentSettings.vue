<template>
  <div class="sub-page payment-page">
    <PageHeader title="微信支付" />
    <div class="page-body">
      <section class="safe-card animate-in">
        <div class="safe-head">
          <div>
            <p>收款安全</p>
            <h1>{{ statusText }}</h1>
          </div>
          <a-tag :class="['state-tag', statusClass]">{{ statusText }}</a-tag>
        </div>
        <div class="safe-copy">订单款项进入商家自己的微信支付商户号，收款账户已锁定，平台不能私自改成其他收款账户。</div>
      </section>

      <section class="mode-card animate-in" style="animation-delay:.04s">
        <div class="mode-head">
          <div>
            <strong>收款模式</strong>
            <span>{{ currentModeTip }}</span>
          </div>
          <a-button type="primary" size="small" :loading="savingMode" @click="savePaymentMode">保存</a-button>
        </div>
        <a-radio-group v-model:value="paymentMode" class="mode-options">
          <a-radio-button value="prepay">先付后厨</a-radio-button>
          <a-radio-button value="postpay">餐后付款</a-radio-button>
          <a-radio-button value="table_account">桌台账单</a-radio-button>
        </a-radio-group>
      </section>

      <section class="info-card animate-in" style="animation-delay:.08s">
        <div class="info-row"><span class="info-label">收款主体</span><span class="info-value">{{ merchant.receiver_name || merchant.name || '-' }}</span></div>
        <div class="info-row"><span class="info-label">微信支付商户号</span><span class="info-value">{{ merchant.wx_mchid_masked || '-' }}</span></div>
        <div class="info-row"><span class="info-label">配置状态</span><span class="info-value">{{ statusText }}</span></div>
        <div class="info-row"><span class="info-label">最后验证时间</span><span class="info-value">{{ merchant.verified_time || '未验证' }}</span></div>
        <div class="info-row last"><span class="info-label">收款账户</span><span class="info-value lock">{{ merchant.payment_locked === false ? '未锁定' : '已锁定' }}</span></div>
      </section>

      <section class="plain-card animate-in" style="animation-delay:.12s">
        <strong>模式说明</strong>
        <span>先付后厨适合快餐和自助点单；餐后付款适合人工收银；桌台账单适合同桌多次加菜后统一结账。若在"桌码管理"里给某张桌码单独设置了分区（简餐区/正餐区），该桌码按分区自动路由，优先于这里的整店默认设置。</span>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import PageHeader from '../../components/PageHeader.vue'
import { getTenantProfile, updateTenantSettings } from '../../api'

const merchant = ref({})
const paymentMode = ref('prepay')
const savingMode = ref(false)

const statusMap = { unconfigured: '未配置', pending: '待验证', verified: '已验证', paused: '暂停' }
const modeTips = {
  prepay: '顾客先完成微信支付，厨房再收到订单',
  postpay: '顾客先下单，商家接单制作，餐后线下收款',
  table_account: '同一桌多次下单，最后由商家统一结账',
}
const statusText = computed(() => statusMap[merchant.value.payment_status] || '未配置')
const statusClass = computed(() => `state-${merchant.value.payment_status || 'unconfigured'}`)
const currentModeTip = computed(() => modeTips[paymentMode.value] || modeTips.prepay)

async function loadProfile() {
  try {
    const res = await getTenantProfile()
    if (res.code === 200 && res.data) {
      merchant.value = res.data
      paymentMode.value = res.data.payment_mode || 'prepay'
    }
  } catch {
    message.error('收款信息加载失败')
  }
}

async function savePaymentMode() {
  savingMode.value = true
  try {
    const res = await updateTenantSettings({ payment_mode: paymentMode.value })
    if (res.code === 200) {
      merchant.value = { ...merchant.value, payment_mode: paymentMode.value }
      message.success('收款模式已保存')
      return
    }
    message.error(res.msg || '保存失败')
  } catch {
    message.error('保存失败')
  } finally {
    savingMode.value = false
  }
}

onMounted(loadProfile)
</script>

<style scoped>
.payment-page { min-height: 100vh; background: var(--bg-page); }
.page-body { padding: 12px 16px 28px; }
.safe-card, .info-card, .plain-card, .mode-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--card-shadow); }
.safe-card { padding: 16px; }
.safe-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.safe-head p, .safe-head h1 { margin: 0; }
.safe-head p { color: var(--success); font-size: 12px; font-weight: 900; }
.safe-head h1 { margin-top: 5px; color: var(--text-1); font-size: 22px; font-weight: 900; }
.safe-copy { margin-top: 12px; padding: 12px; border-radius: 10px; background: var(--brand-light); color: var(--brand-dark); font-size: 13px; line-height: 1.7; }
.mode-card { margin-top: 12px; padding: 14px; }
.mode-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.mode-head strong, .mode-head span { display: block; }
.mode-head strong { color: var(--text-1); font-size: 15px; font-weight: 900; }
.mode-head span { margin-top: 4px; color: var(--text-2); font-size: 12px; line-height: 1.45; }
.mode-options { display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 12px; width: 100%; }
.mode-options :deep(.ant-radio-button-wrapper) { width: 100%; height: 42px; border-radius: 10px; text-align: center; font-weight: 800; line-height: 40px; border-inline-start-width: 1px; }
.mode-options :deep(.ant-radio-button-wrapper:not(:first-child)::before) { display: none; }
.state-tag { margin: 0; border-radius: 14px; font-size: 11px; font-weight: 800; }
.state-verified { color: #16a34a; background: #f0fdf4; border-color: #bbf7d0; }
.state-pending { color: #2563eb; background: #eff6ff; border-color: #bfdbfe; }
.state-paused { color: #6b7280; background: #f8fafc; border-color: #e5e7eb; }
.state-unconfigured { color: #92400e; background: #fffbeb; border-color: #fde68a; }
.info-card { margin-top: 12px; overflow: hidden; }
.info-row.last { border-bottom: 0; }
.lock { color: var(--success) !important; font-weight: 900; }
.plain-card { margin-top: 12px; padding: 14px; }
.plain-card strong, .plain-card span { display: block; }
.plain-card strong { color: var(--text-1); font-size: 15px; font-weight: 900; }
.plain-card span { margin-top: 6px; color: var(--text-2); font-size: 13px; line-height: 1.6; }
</style>