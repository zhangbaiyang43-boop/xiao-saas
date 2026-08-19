/**
 * Phase F1E-B — Merchant Subscription UI logic contract checks.
 * Real function-level assertions against src/utils/subscriptionUi.js
 * (same pattern as test-pickup-no-ui.mjs), not just source-text presence
 * checks -- these actually call the functions with the documented request/
 * response shapes and assert on real return values.
 */
import assert from 'node:assert/strict'
import {
  PLAN_CODE_FREE,
  annualDiscountCopy,
  billingPeriodLabel,
  buildRenewalOrderPayload,
  currentPlanCardCopy,
  formatDate,
  formatPlanPrice,
  formatYuan,
  homeStatusStripCopy,
  isBillingPaymentTerminal,
  isBillingPaymentWaiting,
  manualPaymentStatusCopy,
  mapPurchaseErrorMessage,
  planCardState,
  planDisplayName,
  resolveManualPaymentAvailable,
  resolveOnlinePaymentAvailable,
  trialDisclosure,
} from '../src/utils/subscriptionUi.js'

// ---- FREE_RENDER_TEST -------------------------------------------------
assert.deepEqual(currentPlanCardCopy(null), { title: '免费版', subtitle: '', detail: '', ctaText: '' })
assert.deepEqual(
  currentPlanCardCopy({ subscription_status: 'FREE', effective_plan_code: 'FREE' }),
  { title: '免费版', subtitle: '', detail: '', ctaText: '' },
)

// ---- TRIAL_RENDER_TEST -------------------------------------------------
{
  const copy = currentPlanCardCopy({
    subscription_status: 'TRIAL', effective_plan_code: 'PRO',
    days_remaining: 18, trial_ends_at: '2026-09-04T00:00:00',
  })
  assert.equal(copy.title, '专业版试用中')
  assert.equal(copy.subtitle, '剩余 18 天')
  assert.equal(copy.detail, '试用截止 2026-09-04')
  // 不得出现数据库状态词
  assert.ok(!copy.title.includes('TRIAL'))
}

// ---- ACTIVE_STANDARD_RENDER_TEST ---------------------------------------
{
  const copy = currentPlanCardCopy({
    subscription_status: 'ACTIVE', effective_plan_code: 'STANDARD',
    paid_ends_at: '2027-08-17T00:00:00',
  })
  assert.equal(copy.title, '普通版')
  assert.equal(copy.subtitle, '有效期至 2027-08-17')
  assert.ok(!copy.subtitle.includes('ACTIVE'))
}

// ---- ACTIVE_PRO_RENDER_TEST ---------------------------------------------
{
  const copy = currentPlanCardCopy({
    subscription_status: 'ACTIVE', effective_plan_code: 'PRO',
    paid_ends_at: '2027-08-17T00:00:00',
  })
  assert.equal(copy.title, '专业版')
}

// ---- EXPIRED_RENDER_TEST / CANCELLED ------------------------------------
for (const status of ['EXPIRED', 'CANCELLED']) {
  const copy = currentPlanCardCopy({ subscription_status: status, effective_plan_code: 'STANDARD' })
  assert.equal(copy.title, '套餐已到期，当前使用免费版')
  assert.equal(copy.ctaText, '重新开通')
  assert.ok(!copy.title.includes(status))
}

// ---- Home strip copy (Phase 3) ------------------------------------------
assert.deepEqual(
  homeStatusStripCopy({ subscription_status: 'TRIAL', days_remaining: 5 }),
  { text: '专业版试用中 · 剩余5天', cta: '查看', urgent: false },
)
assert.deepEqual(
  homeStatusStripCopy({ subscription_status: 'ACTIVE', effective_plan_code: 'STANDARD', paid_ends_at: '2027-08-31T00:00:00', days_remaining: 30 }),
  { text: '普通版 · 2027-08-31到期', cta: '查看', urgent: false },
)
// days_remaining <= 14 -> CTA becomes 续费 and urgent=true
assert.deepEqual(
  homeStatusStripCopy({ subscription_status: 'ACTIVE', effective_plan_code: 'PRO', paid_ends_at: '2026-08-25T00:00:00', days_remaining: 7 }),
  { text: '专业版 · 2026-08-25到期', cta: '续费', urgent: true },
)
assert.deepEqual(
  homeStatusStripCopy({ subscription_status: 'EXPIRED' }),
  { text: '套餐已到期，当前使用免费版', cta: '重新开通', urgent: true },
)
assert.deepEqual(
  homeStatusStripCopy({ subscription_status: 'FREE' }),
  { text: '免费版', cta: '升级', urgent: false },
)
assert.equal(homeStatusStripCopy(null), null)

// ---- DEFAULT_MONTH / YEAR_PRICE_TEST -------------------------------------
assert.equal(formatPlanPrice(5900, 'MONTH'), '¥59/月')
assert.equal(formatPlanPrice(9900, 'MONTH'), '¥99/月')
assert.equal(formatPlanPrice(60900, 'YEAR'), '¥609/年')
assert.equal(formatPlanPrice(102200, 'YEAR'), '¥1022/年')

// ---- PRICE_COMES_FROM_API_TEST -------------------------------------------
// Mocked API price with real cents -- proves the formatter is generic, not
// hand-tuned around the four known frozen values.
assert.equal(formatPlanPrice(12345, 'MONTH'), '¥123.45/月')
assert.equal(formatYuan(0), '¥0')
assert.equal(formatYuan(1), '¥0.01')

// ---- Annual discount copy -------------------------------------------------
assert.equal(annualDiscountCopy({ annual_discount_display: '14%' }), '年付省约14%')
assert.equal(annualDiscountCopy({ annual_discount_display: null }), '')
assert.equal(annualDiscountCopy(null), '')

// ---- ACTIVE_STANDARD_PRO_DISABLED_TEST -----------------------------------
{
  const sub = { subscription_status: 'ACTIVE', effective_plan_code: 'STANDARD', ends_at: '2027-01-01' }
  const standardState = planCardState(sub, 'STANDARD')
  const proState = planCardState(sub, 'PRO')
  assert.equal(standardState.enabled, true)
  assert.equal(standardState.isCurrent, true)
  assert.equal(standardState.ctaText, '续费普通版')
  assert.equal(proState.enabled, false)
  assert.equal(proState.disabledReason, '当前套餐到期后可切换')
}

// ---- ACTIVE_PRO_STANDARD_DISABLED_TEST -------------------------------------
{
  const sub = { subscription_status: 'ACTIVE', effective_plan_code: 'PRO' }
  const proState = planCardState(sub, 'PRO')
  const standardState = planCardState(sub, 'STANDARD')
  assert.equal(proState.enabled, true)
  assert.equal(proState.ctaText, '续费专业版')
  assert.equal(standardState.enabled, false)
  assert.equal(standardState.disabledReason, '当前套餐到期后可切换')
}

// ---- FREE plan card: display only, never a CTA -----------------------------
for (const status of ['FREE', 'TRIAL', 'ACTIVE', 'EXPIRED', 'CANCELLED', undefined]) {
  const state = planCardState(status ? { subscription_status: status } : null, PLAN_CODE_FREE)
  assert.equal(state.enabled, false)
  assert.equal(state.ctaText, '')
}

// ---- FREE / TRIAL / EXPIRED / CANCELLED -- STANDARD & PRO purchasable -----
for (const sub of [
  null,
  { subscription_status: 'FREE' },
  { subscription_status: 'TRIAL', effective_plan_code: 'PRO' },
  { subscription_status: 'EXPIRED', effective_plan_code: 'STANDARD' },
  { subscription_status: 'CANCELLED', effective_plan_code: 'PRO' },
]) {
  for (const code of ['STANDARD', 'PRO']) {
    const state = planCardState(sub, code)
    assert.equal(state.enabled, true, `${JSON.stringify(sub)} / ${code} should be purchasable`)
  }
}
// FREE 的开通文案；TRIAL 的购买文案（不同 CTA 措辞，Phase 15）
assert.equal(planCardState({ subscription_status: 'FREE' }, 'STANDARD').ctaText, '开通普通版')
assert.equal(planCardState({ subscription_status: 'TRIAL', effective_plan_code: 'PRO' }, 'PRO').ctaText, '购买专业版')
assert.equal(planCardState({ subscription_status: 'EXPIRED' }, 'PRO').ctaText, '开通专业版')

// ---- TRIAL_STANDARD_DISCLOSURE_TEST -----------------------------------------
{
  const sub = { subscription_status: 'TRIAL', effective_plan_code: 'PRO' }
  const base = trialDisclosure(sub, null)
  assert.ok(base.includes('购买后将立即切换至所选套餐'))
  assert.ok(base.includes('剩余试用天数会自动计入套餐有效期'))
  assert.ok(!base.includes('专业版权益将立即结束'))

  const switchingAway = trialDisclosure(sub, 'STANDARD')
  assert.ok(switchingAway.includes('专业版权益将立即结束'))

  const samePlan = trialDisclosure(sub, 'PRO')
  assert.ok(!samePlan.includes('专业版权益将立即结束'))

  assert.equal(trialDisclosure({ subscription_status: 'ACTIVE' }, 'STANDARD'), '')
  assert.equal(trialDisclosure(null, 'STANDARD'), '')
}

// ---- READINESS_TRUE_ENABLES_CTA_TEST (UI contract only, NOT real WXPAY) ---
assert.equal(
  resolveOnlinePaymentAvailable({ ok: true, data: { online_payment_available: true } }),
  true,
)

// ---- READINESS_REQUEST_FAILURE_FAILS_CLOSED_TEST ---------------------------
assert.equal(resolveOnlinePaymentAvailable(null), false)
assert.equal(resolveOnlinePaymentAvailable(undefined), false)
assert.equal(resolveOnlinePaymentAvailable({ ok: false }), false)
assert.equal(resolveOnlinePaymentAvailable({ ok: true, data: {} }), false)
assert.equal(resolveOnlinePaymentAvailable({ ok: true, data: { online_payment_available: false } }), false)
// truthy-but-not-strictly-true must NOT be treated as available
assert.equal(resolveOnlinePaymentAvailable({ ok: true, data: { online_payment_available: 1 } }), false)
assert.equal(resolveOnlinePaymentAvailable({ ok: true, data: { online_payment_available: 'true' } }), false)

// ---- AMOUNT_NOT_SENT_TEST ---------------------------------------------------
{
  const payload = buildRenewalOrderPayload('STANDARD', 'YEAR')
  assert.deepEqual(Object.keys(payload).sort(), ['billing_period', 'plan_code'])
  assert.deepEqual(payload, { plan_code: 'STANDARD', billing_period: 'YEAR' })
}

// ---- MERCHANT_ERROR_COPY (Phase 22) -----------------------------------------
assert.equal(mapPurchaseErrorMessage("plan not found: 'ENTERPRISE'"), '该套餐暂不可用，请刷新后重试')
assert.equal(mapPurchaseErrorMessage("plan inactive: 'RETIRED'"), '该套餐已下架，请选择其它套餐')
assert.equal(mapPurchaseErrorMessage("invalid billing_period: 'WEEK'"), '请选择月付或年付')
assert.equal(
  mapPurchaseErrorMessage("tenant 't1' has an active paid subscription for a different plan; cannot switch to 'PRO' while active"),
  '当前套餐生效中，到期后才能切换其它套餐',
)
assert.equal(mapPurchaseErrorMessage('REAL PAYMENT BLOCKED BY PLATFORM PAYMENT CONFIG'), '在线支付暂未开放，请稍后再试')
assert.equal(mapPurchaseErrorMessage('some completely unknown backend error'), '续费失败，请稍后重试')
assert.equal(mapPurchaseErrorMessage(undefined), '续费失败，请稍后重试')
// 不得把原始 code 直接抛给商家
assert.notEqual(mapPurchaseErrorMessage("tenant 't1' has an active paid subscription for a different plan; cannot switch to 'PRO' while active"), 'CROSS_PLAN_CHANGE_NOT_ALLOWED')

// ---- Billing payment terminal/waiting classification ------------------------
assert.equal(isBillingPaymentTerminal('PAID'), true)
assert.equal(isBillingPaymentTerminal('FAILED'), true)
assert.equal(isBillingPaymentTerminal('CANCELLED'), true)
assert.equal(isBillingPaymentTerminal('REFUNDED'), true)
assert.equal(isBillingPaymentTerminal('PENDING'), false)
assert.equal(isBillingPaymentWaiting('PENDING'), true)
assert.equal(isBillingPaymentWaiting('PAID'), false)

// ---- misc formatting --------------------------------------------------------
assert.equal(formatDate('2026-08-17T09:30:00'), '2026-08-17')
assert.equal(formatDate(null), '')
assert.equal(formatDate('not-a-date'), '')
assert.equal(planDisplayName('FREE'), '免费版')
assert.equal(planDisplayName('STANDARD'), '普通版')
assert.equal(planDisplayName('PRO'), '专业版')

// ---- MANUAL_READINESS_TRUE_ENABLES_CTA_TEST (Phase F1G-CM-B, UI contract
// only, NOT real WXPAY/real payment) -----------------------------------------
assert.equal(
  resolveManualPaymentAvailable({ ok: true, data: { manual_payment_available: true } }),
  true,
)
// manual=true must never be read as online=true, and vice versa.
assert.equal(
  resolveOnlinePaymentAvailable({ ok: true, data: { online_payment_available: false, manual_payment_available: true } }),
  false,
)
assert.equal(
  resolveManualPaymentAvailable({ ok: true, data: { online_payment_available: true, manual_payment_available: false } }),
  false,
)

// ---- MANUAL_READINESS_REQUEST_FAILURE_FAILS_CLOSED_TEST --------------------
assert.equal(resolveManualPaymentAvailable(null), false)
assert.equal(resolveManualPaymentAvailable(undefined), false)
assert.equal(resolveManualPaymentAvailable({ ok: false }), false)
assert.equal(resolveManualPaymentAvailable({ ok: true, data: {} }), false)
assert.equal(resolveManualPaymentAvailable({ ok: true, data: { manual_payment_available: false } }), false)
assert.equal(resolveManualPaymentAvailable({ ok: true, data: { manual_payment_available: 1 } }), false)
assert.equal(resolveManualPaymentAvailable({ ok: true, data: { manual_payment_available: 'true' } }), false)

// ---- Billing period label ---------------------------------------------------
assert.equal(billingPeriodLabel('YEAR'), '1年')
assert.equal(billingPeriodLabel('MONTH'), '1个月')
assert.equal(billingPeriodLabel(undefined), '1个月')

// ---- Manual payment review status copy (Phase 6 frozen copy) ---------------
{
  const waiting = manualPaymentStatusCopy('WAITING_CONFIRMATION')
  assert.deepEqual(waiting.lines, ['已提交付款确认', '等待平台核实', '通常10分钟内完成，不用重复付款'])
  assert.equal(waiting.actionText, '')
  for (const forbidden of ['支付成功', '付款成功', '已开通']) {
    assert.ok(!waiting.lines.join('').includes(forbidden), `waiting copy must never include: ${forbidden}`)
  }

  const rejected = manualPaymentStatusCopy('REJECTED')
  assert.deepEqual(rejected.lines, ['暂未查到对应款项', '请确认付款后重新提交'])
  assert.equal(rejected.actionText, '重新提交付款确认')

  const initial = manualPaymentStatusCopy(null)
  assert.deepEqual(initial.lines, [])
  assert.equal(initial.actionText, '我已付款')

  assert.equal(manualPaymentStatusCopy('CONFIRMED').actionText, '我已付款')
}

console.log('test-subscription-ui-logic: ok')
