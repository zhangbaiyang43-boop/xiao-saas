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

        <!-- 支付未就绪提示（Phase 17/18，F1G-CM-B 扩展 online/manual 双轨）——
             CTA 已经 disabled，这里只是把 disabled 的原因说清楚，不靠点击后
             报错兜底。online 与 manual 任一可用即可购买，不展示此提示。 -->
        <a-alert
          v-if="!onlinePaymentAvailable && !manualPaymentAvailable"
          class="readiness-banner animate-in"
          type="warning"
          show-icon
          :message="readinessDisabledText"
        />

        <!-- 未完成的人工核实付款（Phase F1G-CM-B §19/§20）——本会话内存态
             恢复入口，不新增 Backend 查询；离开页面后无法自动恢复（记录为
             MANUAL_PAYMENT_RESUME_P1=YES），但不影响真实 Subscription 状态。 -->
        <a-alert
          v-if="manualPayment && !manualModalOpen"
          class="pending-manual-banner animate-in"
          type="info"
          show-icon
          message="有一笔付款待确认"
        >
          <template #action>
            <a-button type="link" size="small" @click="manualModalOpen = true">查看</a-button>
          </template>
        </a-alert>

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
              :disabled="!(onlinePaymentAvailable || manualPaymentAvailable) || purchaseSubmitting"
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

    <!-- 人工核实付款（Phase F1G-CM-B）：仅商户侧 CLAIM 界面，绝不在此处
         把 BillingInvoice/BillingPayment 标记为已支付——那只能来自 SuperAdmin
         confirm 之后的真实轮询结果。 -->
    <a-modal
      :open="manualModalOpen"
      :title="manualPaymentTitle"
      :footer="null"
      :closable="!manualClaimSubmitting"
      :mask-closable="false"
      centered
      class="manual-payment-modal"
      @cancel="closeManualModal"
    >
      <template v-if="manualPayment">
        <p class="mp-amount">{{ manualAmountText }}</p>
        <p class="mp-period">{{ manualPeriodText }}</p>

        <template v-if="!manualPayment.manual_review_status">
          <p class="mp-method">微信扫码付款</p>
          <div class="mp-qr">
            <img
              v-if="manualPayment.qr_url && !qrLoadError"
              :src="manualPayment.qr_url"
              alt="收款二维码"
              @error="onQrError"
            />
            <div v-else class="mp-qr-error">付款二维码暂不可用<br />请稍后重试</div>
          </div>
        </template>

        <div class="mp-field">
          <span class="mp-field-label">收款方</span>
          <span class="mp-field-value">{{ manualPayment.payee_name || '—' }}</span>
        </div>
        <div class="mp-field mp-field--out-trade-no">
          <span class="mp-field-label">账单号</span>
          <span class="mp-field-value mp-out-trade-no">{{ manualPayment.out_trade_no }}</span>
          <a-button type="link" size="small" @click="copyOutTradeNo">复制</a-button>
        </div>

        <template v-if="!manualPayment.manual_review_status">
          <a-button
            type="primary"
            block
            style="margin-top:12px"
            :loading="manualClaimSubmitting"
            :disabled="qrLoadError"
            @click="handleManualClaim"
          >我已付款</a-button>
          <p class="mp-hint">付款完成后点击"我已付款"，通常10分钟内确认开通</p>
        </template>

        <template v-else-if="manualPayment.manual_review_status === 'WAITING_CONFIRMATION'">
          <div class="mp-waiting">
            <p v-for="line in manualStatusCopy.lines" :key="line">{{ line }}</p>
          </div>
        </template>

        <template v-else-if="manualPayment.manual_review_status === 'REJECTED'">
          <div class="mp-rejected">
            <p v-for="line in manualStatusCopy.lines" :key="line">{{ line }}</p>
          </div>
          <a-button
            type="primary"
            block
            style="margin-top:12px"
            :loading="manualClaimSubmitting"
            @click="handleManualClaim"
          >{{ manualStatusCopy.actionText }}</a-button>
        </template>

        <a-button block style="margin-top:8px" @click="closeManualModal">返回</a-button>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import PageHeader from '../../components/PageHeader.vue'
import {
  claimManualBillingPayment,
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
  billingPeriodLabel,
  buildRenewalOrderPayload,
  currentPlanCardCopy,
  formatDate,
  formatPlanPrice,
  formatYuan,
  isBillingPaymentTerminal,
  manualPaymentStatusCopy,
  mapPurchaseErrorMessage,
  planCardState,
  planDisplayName,
  resolveManualPaymentAvailable,
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
const manualPaymentAvailable = ref(false)
const readinessKnown = ref(false)
const billingPeriod = ref('MONTH')
const purchaseSubmitting = ref(false)
const pendingPurchasePlanCode = ref('')
const purchaseSuccess = ref(null)

// ---- 人工核实付款（Phase F1G-CM-B）。manualPayment 在内存中保留直到
// PAID 或用户离开本组件实例，用来支撑同会话内的"查看"恢复入口——不新增
// Backend 查询接口（MANUAL_PAYMENT_RESUME_P1=YES）。 ----
const manualPayment = ref(null)
const manualModalOpen = ref(false)
const manualClaimSubmitting = ref(false)
const qrLoadError = ref(false)
const manualPaymentTitle = ref('')

const manualStatusCopy = computed(() => manualPaymentStatusCopy(manualPayment.value?.manual_review_status))
const manualAmountText = computed(() => formatYuan(manualPayment.value?.amount_cents))
const manualPeriodText = computed(() => billingPeriodLabel(manualPayment.value?.billing_period))

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

  // Fail closed（Phase 18，F1G-CM-B 扩展 manual 轨道）：只有请求成功且明确
  // 返回 true 才判定可购买；请求失败/异常一律留在初始的 false，不得默认放行。
  if (readinessRes.status === 'fulfilled' && readinessRes.value?.code === 200) {
    readinessKnown.value = true
    onlinePaymentAvailable.value = resolveOnlinePaymentAvailable({ ok: true, data: readinessRes.value.data })
    manualPaymentAvailable.value = resolveManualPaymentAvailable({ ok: true, data: readinessRes.value.data })
  } else {
    readinessKnown.value = false
    onlinePaymentAvailable.value = false
    manualPaymentAvailable.value = false
  }

  loading.value = false
}

function handlePurchaseClick(planCode) {
  if (purchaseSubmitting.value) return
  // CTA 已经在渲染层用 :disabled 挡住，这里是二次防御，绝不依赖点击后
  // 才发现 online/manual 都不可用（Phase 17，F1G-CM-B 扩展 manual 轨道）。
  if (!onlinePaymentAvailable.value && !manualPaymentAvailable.value) return

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
    // provider——那是仅供内部/测试使用的能力，见 F1E-A 冻结语义。本阶段
    // online_payment_available 恒为 false，实际必然走 MANUAL；WXPAY 分支
    // 保留给未来 online 就绪时使用，不在本阶段被触达。
    const provider = onlinePaymentAvailable.value ? 'WXPAY' : 'MANUAL'
    const paymentRes = await createBillingPayment(invoiceId, { provider })
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

    if (provider === 'MANUAL') {
      const payParams = paymentRes.data?.provider?.pay_params || {}
      manualPaymentTitle.value = cardStateFor(planCode).ctaText || '开通套餐'
      manualPayment.value = {
        ...payment,
        plan_code: planCode,
        billing_period: billingPeriod.value,
        payee_name: payParams.payee_name || '',
        qr_url: payParams.qr_url || '',
      }
      qrLoadError.value = false
      manualModalOpen.value = true
      purchaseSubmitting.value = false
      return
    }

    startPaymentPolling(payment.id)
  } catch (err) {
    message.error(mapPurchaseErrorMessage(err?.response?.data?.msg))
    purchaseSubmitting.value = false
  }
}

function mergeManualPayment(payment) {
  if (!manualPayment.value || !payment) return
  manualPayment.value = { ...manualPayment.value, ...payment }
}

function onQrError() {
  qrLoadError.value = true
}

async function copyOutTradeNo() {
  const text = manualPayment.value?.out_trade_no
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制账单号')
  } catch {
    // 复制失败不影响付款流程（Phase 11），静默即可。
  }
}

function closeManualModal() {
  if (manualClaimSubmitting.value) return
  manualModalOpen.value = false
}

async function handleManualClaim() {
  // Loading lock 防止连续快速点击重复创建请求（Phase 12/13）；Backend
  // 自身也保证幂等，这里只是前端的第一道防御。
  if (manualClaimSubmitting.value || !manualPayment.value?.id) return
  manualClaimSubmitting.value = true
  try {
    const res = await claimManualBillingPayment(manualPayment.value.id)
    if (res?.code !== 200) {
      message.error(mapPurchaseErrorMessage(res?.msg))
      manualClaimSubmitting.value = false
      return
    }
    mergeManualPayment(res.data)
    manualClaimSubmitting.value = false
    pendingPurchasePlanCode.value = manualPayment.value.plan_code
    startPaymentPolling(manualPayment.value.id)
  } catch (err) {
    message.error(mapPurchaseErrorMessage(err?.response?.data?.msg))
    manualClaimSubmitting.value = false
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
    manualModalOpen.value = false
    manualPayment.value = null
    manualClaimSubmitting.value = false
    await loadPage()
    purchaseSubmitting.value = false
    purchaseSuccess.value = {
      planName: planDisplayName(planCode),
      endsAtText: formatDate(currentSubscription.value?.paid_ends_at),
    }
    return
  }

  // MANUAL 支付：只读轮询 manual_review_status，绝不在前端把这当作
  // "已支付"——只有真正的 status === 'PAID'（来自 SuperAdmin confirm 触发
  // 的 process_verified_payment_fact()）才算数（Phase F1G-CM-B 安全冻结）。
  if (payment.provider === 'MANUAL') {
    mergeManualPayment(payment)
    if (payment.manual_review_status === 'REJECTED') {
      // 驳回后不再自动轮询，等待商家重新提交 claim 才重启轮询。
      stopBillingPaymentPolling()
      manualClaimSubmitting.value = false
    }
    return
  }

  if (isBillingPaymentTerminal(payment.status)) {
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
/* .sub-page 的全局底部留白（32px + 安全区）没有把固定 TabBar 算进去——
   Layout.vue 对所有路由都无条件渲染 <TabBar/>，包括这个通过 PageHeader
   返回按钮进入的“子页面”。这里按 .page-wrap 里已经在用的同一套算法
   （TabBar 自身高度 56px + safe-area-inset-bottom + 视觉留白）单独把
   最后一张套餐卡的 CTA 让出来，不改 .sub-page/.bottom-tabbar 全局定义，
   避免影响其它同样用 .sub-page 但没有这个问题的页面。 */
.page-body { padding: 12px 16px calc(56px + env(safe-area-inset-bottom) + 12px); }

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
.pending-manual-banner { margin-bottom: 12px; border-radius: 10px; }
.pending-manual-banner :deep(.ant-alert-content) { display: flex; align-items: center; justify-content: space-between; gap: 8px; }

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

/* 人工核实付款弹层（Phase F1G-CM-B）——只展示商家能理解的字段，绝不
   暴露 payment id / invoice id / provider / manual_review_status 等内部
   技术状态（Phase 40）。 */
.manual-payment-modal .mp-amount { margin: 0; color: var(--text-1); font-size: 26px; font-weight: 900; text-align: center; }
.manual-payment-modal .mp-period { margin: 4px 0 14px; color: var(--text-2); font-size: 13px; text-align: center; }
.manual-payment-modal .mp-method { margin: 0 0 8px; color: var(--text-2); font-size: 13px; text-align: center; }
.manual-payment-modal .mp-qr { display: flex; align-items: center; justify-content: center; width: 220px; height: 220px; margin: 0 auto 14px; background: var(--bg-page); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.manual-payment-modal .mp-qr img { width: 100%; height: 100%; object-fit: contain; }
.manual-payment-modal .mp-qr-error { padding: 0 16px; color: var(--text-3); font-size: 12px; text-align: center; line-height: 1.6; }
.manual-payment-modal .mp-field { display: flex; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.manual-payment-modal .mp-field-label { flex: 0 0 auto; color: var(--text-3); font-size: 13px; }
.manual-payment-modal .mp-field-value { flex: 1; min-width: 0; color: var(--text-1); font-size: 13px; word-break: break-all; }
.manual-payment-modal .mp-out-trade-no { font-family: 'SFMono-Regular', Consolas, monospace; }
.manual-payment-modal .mp-hint { margin: 10px 0 0; color: var(--text-3); font-size: 12px; text-align: center; line-height: 1.6; }
.manual-payment-modal .mp-waiting,
.manual-payment-modal .mp-rejected { padding: 14px 0 0; text-align: center; }
.manual-payment-modal .mp-waiting p,
.manual-payment-modal .mp-rejected p { margin: 0 0 4px; color: var(--text-2); font-size: 13px; line-height: 1.6; }
.manual-payment-modal .mp-waiting p:first-child,
.manual-payment-modal .mp-rejected p:first-child { color: var(--text-1); font-size: 15px; font-weight: 700; }
</style>
