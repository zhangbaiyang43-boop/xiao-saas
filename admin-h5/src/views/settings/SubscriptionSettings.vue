<template>
  <div class="sub-page subscription-page">
    <PageHeader title="我的套餐" />
    <div class="page-body">
      <!-- 加载失败：不隐藏页面，给一个明确的重试入口（Phase 28） -->
      <section v-if="loadError && !loading" class="state-card animate-in">
        <p>套餐信息加载失败</p>
        <a-button type="primary" :loading="loading" @click="loadPage">重试</a-button>
      </section>

      <template v-else>
        <!-- A. 当前套餐状态卡 -->
        <section class="current-card animate-in">
          <p class="current-eyebrow">当前套餐</p>
          <h1>{{ currentCard.title }}</h1>
          <span v-if="currentCard.subtitle">{{ currentCard.subtitle }}</span>
          <span v-if="currentCard.detail" class="current-detail">{{ currentCard.detail }}</span>
        </section>

        <!-- Trial 常驻披露：不能等点了购买按钮才解释 -->
        <a-alert
          v-if="isTrial"
          class="trial-disclosure animate-in"
          type="info"
          show-icon
          :message="trialDisclosureText"
          banner
        />

        <!-- B. 月付/年付 segmented control，默认 MONTH -->
        <section class="period-card animate-in" style="animation-delay:.04s">
          <a-radio-group v-model:value="billingPeriod" class="period-options">
            <a-radio-button value="MONTH">月付</a-radio-button>
            <a-radio-button value="YEAR">年付</a-radio-button>
          </a-radio-group>
        </section>

        <!-- 在线支付未就绪提示（Phase 17/18）——CTA 已经 disabled，这里只是把
             disabled 的原因说清楚，不靠点击后报错兜底。 -->
        <a-alert
          v-if="!onlinePaymentAvailable"
          class="readiness-banner animate-in"
          type="warning"
          show-icon
          :message="readinessDisabledText"
        />

        <!-- C/D/E. 套餐卡片：FREE 只展示，STANDARD/PRO 带价格与 CTA -->
        <section
          v-for="plan in orderedPlans"
          :key="plan.plan_code"
          class="plan-card animate-in"
          :class="{ 'plan-card--current': cardStateFor(plan.plan_code).isCurrent }"
        >
          <div class="plan-head">
            <div>
              <strong>{{ plan.display_name }}</strong>
              <a-tag v-if="cardStateFor(plan.plan_code).isCurrent" class="current-tag">当前</a-tag>
            </div>
            <div class="plan-price">
              <span class="plan-price-main">{{ formatPlanPrice(priceCentsFor(plan), billingPeriod) }}</span>
              <span v-if="billingPeriod === 'YEAR' && annualDiscountCopy(plan)" class="plan-price-discount">{{ annualDiscountCopy(plan) }}</span>
            </div>
          </div>

          <ul class="plan-bullets">
            <li v-for="bullet in planBullets(plan.plan_code)" :key="bullet">{{ bullet }}</li>
          </ul>

          <template v-if="plan.plan_code !== PLAN_CODE_FREE">
            <a-button
              v-if="cardStateFor(plan.plan_code).enabled"
              type="primary"
              block
              :disabled="!onlinePaymentAvailable || purchaseSubmitting"
              :loading="purchaseSubmitting && pendingPurchasePlanCode === plan.plan_code"
              @click="handlePurchaseClick(plan.plan_code)"
            >{{ cardStateFor(plan.plan_code).ctaText }}</a-button>
            <div v-else class="plan-disabled-reason">{{ cardStateFor(plan.plan_code).disabledReason }}</div>
          </template>
        </section>
      </template>
    </div>

    <!-- 支付成功（Phase 21）：无庆祝动画，简单信息 + 完成 -->
    <a-modal
      :open="!!purchaseSuccess"
      title="续费成功"
      :footer="null"
      :closable="false"
      centered
    >
      <p class="success-line">{{ purchaseSuccess?.planName }}已开通</p>
      <p v-if="purchaseSuccess?.endsAtText" class="success-line success-line--muted">有效期至：{{ purchaseSuccess.endsAtText }}</p>
      <a-button type="primary" block style="margin-top:16px" @click="purchaseSuccess = null">完成</a-button>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import PageHeader from '../../components/PageHeader.vue'
import {
  createBillingPayment,
  createRenewalOrder,
  getBillingPayment,
  getCurrentSubscription,
  getPaymentReadiness,
  getSubscriptionPlans,
} from '../../api'
import {
  PLAN_CODE_FREE,
  annualDiscountCopy,
  buildRenewalOrderPayload,
  currentPlanCardCopy,
  formatDate,
  formatPlanPrice,
  isBillingPaymentTerminal,
  mapPurchaseErrorMessage,
  planCardState,
  planDisplayName,
  resolveOnlinePaymentAvailable,
  trialDisclosure,
} from '../../utils/subscriptionUi'

// 冻结文案（Phase F1E0 §14 / 本阶段 §11）——只能是这三条，不得追加任何
// 尚未在代码里验证存在的能力宣传。
const PLAN_BULLETS = {
  FREE: ['扫码点单与菜单', '订单与微信收款', '长期免费'],
  STANDARD: ['后厨自动出票', '多员工协同', '智能菜单工具'],
  PRO: ['会员积分体系', '优惠券与自动营销', '渠道拉新与分销'],
}
function planBullets(planCode) {
  return PLAN_BULLETS[planCode] || []
}

const loading = ref(true)
const loadError = ref(false)
const currentSubscription = ref(null)
const plans = ref([])
const onlinePaymentAvailable = ref(false)
const readinessKnown = ref(false)
const billingPeriod = ref('MONTH')
const purchaseSubmitting = ref(false)
const pendingPurchasePlanCode = ref('')
const purchaseSuccess = ref(null)

const currentCard = computed(() => currentPlanCardCopy(currentSubscription.value))
const isTrial = computed(() => currentSubscription.value?.subscription_status === 'TRIAL')
const trialDisclosureText = computed(() => trialDisclosure(currentSubscription.value, null))
const readinessDisabledText = computed(() => (readinessKnown.value ? '在线续费即将开放' : '在线续费暂不可用'))

// 展示顺序固定 FREE/STANDARD/PRO，不依赖后端返回顺序。
const PLAN_ORDER = [PLAN_CODE_FREE, 'STANDARD', 'PRO']
const orderedPlans = computed(() => {
  const byCode = Object.fromEntries(plans.value.map(p => [p.plan_code, p]))
  return PLAN_ORDER.map(code => byCode[code]).filter(Boolean)
})

function cardStateFor(planCode) {
  return planCardState(currentSubscription.value, planCode)
}

function priceCentsFor(plan) {
  return billingPeriod.value === 'YEAR' ? plan.price_year_cents : plan.price_month_cents
}

function planByCode(code) {
  return plans.value.find(p => p.plan_code === code) || null
}

async function loadPage() {
  loading.value = true
  loadError.value = false

  const [subRes, plansRes, readinessRes] = await Promise.allSettled([
    getCurrentSubscription(),
    getSubscriptionPlans(),
    getPaymentReadiness({ meta: { dedupe: true, dedupeKey: 'subscription:readiness' } }),
  ])

  if (subRes.status === 'fulfilled' && subRes.value?.code === 200) {
    currentSubscription.value = subRes.value.data
  } else {
    loadError.value = true
  }

  if (plansRes.status === 'fulfilled' && plansRes.value?.code === 200) {
    plans.value = plansRes.value.data || []
  } else {
    loadError.value = true
  }

  // Fail closed（Phase 18）：只有请求成功且明确返回 true 才判定可购买；
  // 请求失败/异常一律留在初始的 false，不得默认放行。
  if (readinessRes.status === 'fulfilled' && readinessRes.value?.code === 200) {
    readinessKnown.value = true
    onlinePaymentAvailable.value = resolveOnlinePaymentAvailable({ ok: true, data: readinessRes.value.data })
  } else {
    readinessKnown.value = false
    onlinePaymentAvailable.value = false
  }

  loading.value = false
}

function handlePurchaseClick(planCode) {
  if (purchaseSubmitting.value) return
  // CTA 已经在渲染层用 :disabled 挡住，这里是二次防御，绝不依赖点击后
  // 才发现 online_payment_available=false（Phase 17）。
  if (!onlinePaymentAvailable.value) return

  const plan = planByCode(planCode)
  const priceText = plan ? formatPlanPrice(priceCentsFor(plan), billingPeriod.value) : ''
  const disclosure = isTrial.value ? trialDisclosure(currentSubscription.value, planCode) : ''
  const ctaText = cardStateFor(planCode).ctaText || '购买'

  Modal.confirm({
    title: `确认${ctaText}`,
    content: disclosure ? `${priceText}\n${disclosure}` : `${priceText}`,
    okText: '确认',
    onOk: () => submitPurchase(planCode),
  })
}

async function submitPurchase(planCode) {
  purchaseSubmitting.value = true
  pendingPurchasePlanCode.value = planCode
  try {
    const orderRes = await createRenewalOrder(buildRenewalOrderPayload(planCode, billingPeriod.value))
    if (orderRes?.code !== 200) {
      message.error(mapPurchaseErrorMessage(orderRes?.msg))
      purchaseSubmitting.value = false
      return
    }
    const invoiceId = orderRes.data.invoice_id
    // 商家真实购买流程只能走真实支付渠道，绝不能悄悄落到默认的 FAKE
    // provider——那是仅供内部/测试使用的能力，见 F1E-A 冻结语义。
    const paymentRes = await createBillingPayment(invoiceId, { provider: 'WXPAY' })
    if (paymentRes?.code !== 200) {
      message.error(mapPurchaseErrorMessage(paymentRes?.msg))
      purchaseSubmitting.value = false
      return
    }
    const payment = paymentRes.data?.payment
    if (!payment?.id) {
      purchaseSubmitting.value = false
      message.error('续费失败，请稍后重试')
      return
    }
    startPaymentPolling(payment.id)
  } catch (err) {
    message.error(mapPurchaseErrorMessage(err?.response?.data?.msg))
    purchaseSubmitting.value = false
  }
}

// ---- 支付状态轮询：与 AssistedOrderSheet.vue 的 payment-handoff 轮询同一
// 形状（chained setTimeout，单飞行守卫，隐藏时暂停，可见时恢复，有限次数
// 上限），不发明第二套轮询实现。 ----
const paymentStatusTimer = ref(null)
const paymentStatusInFlight = ref(false)
const paymentPollingActive = ref(false)
const pollingPaymentId = ref(null)
const paymentStatusAttempts = ref(0)
const PAYMENT_STATUS_POLL_INTERVAL_MS = 2500
const PAYMENT_STATUS_MAX_ATTEMPTS = 120

function clearPaymentStatusTimer() {
  if (paymentStatusTimer.value) {
    clearTimeout(paymentStatusTimer.value)
    paymentStatusTimer.value = null
  }
}

function shouldPollBillingPayment() {
  if (!paymentPollingActive.value || !pollingPaymentId.value) return false
  if (typeof document !== 'undefined' && document.hidden) return false
  if (paymentStatusAttempts.value >= PAYMENT_STATUS_MAX_ATTEMPTS) return false
  return true
}

function stopBillingPaymentPolling() {
  paymentPollingActive.value = false
  clearPaymentStatusTimer()
}

function schedulePaymentStatusCheck() {
  clearPaymentStatusTimer()
  if (!shouldPollBillingPayment()) return
  paymentStatusTimer.value = setTimeout(() => {
    paymentStatusTimer.value = null
    void checkBillingPaymentStatus({ scheduleAfter: true })
  }, PAYMENT_STATUS_POLL_INTERVAL_MS)
}

async function checkBillingPaymentStatus({ scheduleAfter = true } = {}) {
  if (paymentStatusInFlight.value) return { skipped: true }
  const paymentId = pollingPaymentId.value
  if (!paymentPollingActive.value || !paymentId || (typeof document !== 'undefined' && document.hidden)) {
    clearPaymentStatusTimer()
    return { skipped: true }
  }
  paymentStatusInFlight.value = true
  paymentStatusAttempts.value += 1
  try {
    const res = await getBillingPayment(paymentId, {
      meta: { fromPolling: true, dedupe: true, dedupeKey: `billing-payment:${paymentId}` },
    })
    const data = res?.data || res
    if (String(pollingPaymentId.value) === String(paymentId) && data) {
      await handleBillingPaymentUpdate(data)
    }
    return { skipped: false }
  } catch (err) {
    return { skipped: false, error: err }
  } finally {
    paymentStatusInFlight.value = false
    if (paymentStatusAttempts.value >= PAYMENT_STATUS_MAX_ATTEMPTS) {
      stopBillingPaymentPolling()
      if (purchaseSubmitting.value) {
        purchaseSubmitting.value = false
        message.warning('支付确认超时，可稍后重新查看套餐状态')
      }
    } else if (scheduleAfter) {
      schedulePaymentStatusCheck()
    }
  }
}

async function handleBillingPaymentUpdate(payment) {
  if (payment.status === 'PAID') {
    stopBillingPaymentPolling()
    const planCode = pendingPurchasePlanCode.value
    await loadPage()
    purchaseSubmitting.value = false
    purchaseSuccess.value = {
      planName: planDisplayName(planCode),
      endsAtText: formatDate(currentSubscription.value?.paid_ends_at),
    }
  } else if (isBillingPaymentTerminal(payment.status)) {
    stopBillingPaymentPolling()
    purchaseSubmitting.value = false
    message.error('支付未完成，请重试')
  }
}

function startPaymentPolling(paymentId) {
  pollingPaymentId.value = paymentId
  paymentStatusAttempts.value = 0
  clearPaymentStatusTimer()
  paymentPollingActive.value = true
  void checkBillingPaymentStatus({ scheduleAfter: true })
}

function onPaymentVisibilityChange() {
  if (typeof document === 'undefined') return
  if (document.hidden) {
    clearPaymentStatusTimer()
    return
  }
  if (shouldPollBillingPayment()) void checkBillingPaymentStatus({ scheduleAfter: true })
}

onMounted(() => {
  loadPage()
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onPaymentVisibilityChange)
})
onBeforeUnmount(() => {
  stopBillingPaymentPolling()
  if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onPaymentVisibilityChange)
})
</script>

<style scoped>
.subscription-page { min-height: 100vh; background: var(--bg-page); }
.page-body { padding: 12px 16px 28px; }

.state-card, .current-card, .period-card, .plan-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: var(--card-shadow);
}

.state-card { padding: 24px; text-align: center; }
.state-card p { color: var(--text-2); margin: 0 0 12px; }

.current-card { padding: 18px; margin-bottom: 12px; }
.current-eyebrow { margin: 0; color: var(--text-3); font-size: 12px; font-weight: 700; }
.current-card h1 { margin: 6px 0 0; color: var(--text-1); font-size: 22px; font-weight: 900; }
.current-card span { display: block; margin-top: 6px; color: var(--text-2); font-size: 13px; }
.current-detail { color: var(--text-3) !important; font-size: 12px !important; }

.trial-disclosure { margin-bottom: 12px; border-radius: 10px; }
.readiness-banner { margin-bottom: 12px; border-radius: 10px; }

.period-card { padding: 12px; margin-bottom: 12px; }
.period-options { display: flex; width: 100%; }
.period-options :deep(.ant-radio-button-wrapper) {
  flex: 1;
  text-align: center;
  height: 40px;
  line-height: 38px;
  border-radius: 10px;
}

.plan-card { padding: 16px; margin-bottom: 12px; }
.plan-card--current { border-color: var(--brand); }
.plan-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.plan-head strong { color: var(--text-1); font-size: 17px; font-weight: 900; }
.current-tag { margin-left: 8px; color: var(--success); background: var(--brand-light); border-color: var(--brand-mid); border-radius: 10px; font-size: 11px; font-weight: 800; }
.plan-price { text-align: right; }
.plan-price-main { display: block; color: var(--text-1); font-size: 18px; font-weight: 900; }
.plan-price-discount { display: block; margin-top: 2px; color: var(--success); font-size: 11px; font-weight: 700; }

.plan-bullets { list-style: none; margin: 12px 0 14px; padding: 0; }
.plan-bullets li { position: relative; padding-left: 16px; margin-top: 6px; color: var(--text-2); font-size: 13px; line-height: 1.5; }
.plan-bullets li::before { content: '·'; position: absolute; left: 0; color: var(--brand); font-weight: 900; }

.plan-disabled-reason { padding: 10px 0 0; color: var(--text-3); font-size: 12px; text-align: center; }

.success-line { margin: 0 0 6px; color: var(--text-1); font-size: 15px; font-weight: 700; text-align: center; }
.success-line--muted { color: var(--text-2); font-size: 13px; font-weight: 400; }
</style>
