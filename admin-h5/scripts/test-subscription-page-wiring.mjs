/**
 * Phase F1E-B — SubscriptionSettings.vue source-contract checks.
 *
 * No component-render framework exists in this repo (see
 * test-payment-handoff-polling.mjs precedent) -- these are structural /
 * text-presence assertions on the actual source, same convention as every
 * other scripts/test-*.mjs file. Real logic (price formatting, plan-card
 * state, readiness fail-closed) is unit-tested with genuine function calls
 * in test-subscription-ui-logic.mjs; this file proves the component wires
 * that logic in correctly and doesn't bypass it.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'src/views/settings/SubscriptionSettings.vue'), 'utf8')

function indexOfOrFail(text, label) {
  const i = source.indexOf(text)
  assert.ok(i !== -1, `expected to find: ${label}`)
  return i
}

// ---- DEFAULT_MONTH_TEST -----------------------------------------------
assert.ok(source.includes("billingPeriod = ref('MONTH')"), 'default billing period must be MONTH')
assert.ok(!source.includes("billingPeriod = ref('YEAR')"), 'must not default to YEAR')

// ---- PRICE_COMES_FROM_API_TEST: no hardcoded cents anywhere -------------
for (const hardcoded of ['5900', '60900', '9900', '102200']) {
  assert.ok(!source.includes(hardcoded), `must not hardcode price cents literal ${hardcoded}`)
}
assert.ok(source.includes('formatPlanPrice('), 'prices must be rendered via the shared formatter, not inline math')
assert.ok(source.includes('priceCentsFor('), 'price must come from the plan object returned by the API')

// ---- ANNUAL_DISCOUNT_UI: no computed monthly-equivalent price -----------
assert.ok(!/toFixed\(2\).*\/\s*12/.test(source), 'must not compute a monthly-equivalent price from the annual price')
assert.ok(source.includes('annualDiscountCopy('), 'annual discount label must come from the shared helper, not inline text')

// ---- READINESS_FALSE_DISABLES_CTA_TEST: renewal-orders must not be
// reachable when online payment is unavailable -----------------------------
{
  const guardIdx = indexOfOrFail('if (!onlinePaymentAvailable.value) return', 'readiness guard in handlePurchaseClick')
  const createOrderCallIdx = indexOfOrFail('await createRenewalOrder(', 'createRenewalOrder call site')
  assert.ok(guardIdx < createOrderCallIdx, 'the readiness guard must appear before the renewal-orders call')
  // The template must also bind :disabled to onlinePaymentAvailable so a
  // real click can never reach the handler in the first place.
  assert.ok(source.includes(':disabled="!onlinePaymentAvailable'), 'purchase CTA must be template-disabled when readiness is false')
}

// ---- READINESS_FAILURE_BEHAVIOR: fail closed on request failure ---------
{
  const loadFnIdx = indexOfOrFail('async function loadPage()', 'loadPage function')
  const readinessBlock = source.slice(loadFnIdx)
  assert.ok(readinessBlock.includes('readinessKnown.value = false'), 'readiness must default/reset to unknown-false on failure')
  assert.ok(readinessBlock.includes('onlinePaymentAvailable.value = false'), 'readiness must reset to unavailable on failure')
}
assert.ok(source.includes('resolveOnlinePaymentAvailable('), 'must use the shared fail-closed readiness resolver, not ad-hoc logic')

// ---- Real payment provider only, never FAKE for merchant purchases ------
assert.ok(source.includes("provider: 'WXPAY'"), 'merchant purchase flow must request the real WXPAY provider')
assert.ok(!source.includes("provider: 'FAKE'"), 'merchant purchase flow must never request the FAKE provider')

// ---- AMOUNT_NOT_SENT_TEST: renewal order body built via the shared,
// key-limited payload builder -----------------------------------------------
assert.ok(source.includes('buildRenewalOrderPayload(planCode, billingPeriod.value)'), 'renewal order body must go through buildRenewalOrderPayload')
assert.ok(!/createRenewalOrder\(\s*\{/.test(source), 'must not construct the renewal-order body as an inline object literal')

// ---- ADMIN_PAYMENT_FLOW_WIRING_TEST (source-contract level; NOT
// REAL_PAYMENT_E2E) -- renewal order -> payment attempt -> polling ->
// current-subscription refresh, in that order. -----------------------------
{
  const orderIdx = indexOfOrFail('await createRenewalOrder(', 'renewal order call')
  const paymentIdx = indexOfOrFail('await createBillingPayment(', 'payment attempt call')
  const pollIdx = indexOfOrFail('startPaymentPolling(payment.id)', 'poll start call')
  assert.ok(orderIdx < paymentIdx, 'renewal order must be created before the payment attempt')
  assert.ok(paymentIdx < pollIdx, 'payment attempt must be created before polling starts')

  const paidHandlerIdx = indexOfOrFail("payment.status === 'PAID'", 'PAID branch of payment status handling')
  const refreshIdx = indexOfOrFail('await loadPage()', 'current-subscription refresh on PAID')
  assert.ok(paidHandlerIdx < refreshIdx, 'reaching PAID must trigger a current-subscription refresh')
}

// ---- Polling shape: same contract as test-payment-handoff-polling.mjs ---
function countText(text) { return source.split(text).length - 1 }
assert.equal(countText('setInterval('), 0, 'billing payment polling must not use setInterval')
assert.ok(source.includes('setTimeout('), 'billing payment polling must use chained setTimeout')
assert.ok(source.includes('clearTimeout('), 'billing payment polling must clear timeout handles')
assert.ok(source.includes('paymentStatusInFlight'), 'billing payment polling must have an in-flight guard')
assert.ok(source.includes('checkBillingPaymentStatus'), 'billing payment status checks must use one entry point')
assert.ok(source.includes('schedulePaymentStatusCheck'), 'billing payment polling must use one scheduler')
assert.ok(source.includes('clearPaymentStatusTimer'), 'billing payment polling must use one clear helper')
assert.ok(source.includes('document.hidden'), 'billing payment polling must pause while hidden')
assert.ok(source.includes('visibilitychange'), 'billing payment polling must listen for visibility changes')
assert.ok(source.includes("addEventListener('visibilitychange'"), 'visibility listener must be registered')
assert.ok(source.includes("removeEventListener('visibilitychange'"), 'visibility listener must be removed on unmount')
assert.ok(source.includes('PAYMENT_STATUS_MAX_ATTEMPTS'), 'billing payment polling must have a bounded attempt cap, not poll forever')
assert.ok(source.includes('onBeforeUnmount'), 'polling must be torn down on unmount')

// ---- Trial disclosure must be persistent, not only inside a click handler -
{
  const templateEnd = source.indexOf('</template>')
  const template = source.slice(0, templateEnd)
  assert.ok(template.includes('trial-disclosure'), 'trial disclosure must be a persistent element in the template, not only shown after a click')
  assert.ok(template.includes('v-if="isTrial"'), 'trial disclosure visibility must be tied to the TRIAL status')
}

// ---- Purchase success UX: no busy animation, simple copy -----------------
assert.ok(source.includes('续费成功'), 'success screen must use the frozen copy')
assert.ok(source.includes('已开通'), 'success screen must state which plan was opened')
assert.ok(source.includes('有效期至'), 'success screen must show the new paid-through date')
assert.ok(source.includes('完成'), 'success screen must have a 完成 action')
assert.ok(!/animate__|lottie|confetti/i.test(source), 'success screen must not use a celebration animation library')

// ---- Purchase submission must be reentrancy-guarded (Phase 28) ----------
assert.ok(source.includes('if (purchaseSubmitting.value) return'), 'purchase click must guard against double submission')
assert.ok(source.includes(':loading="purchaseSubmitting'), 'purchase CTA must show a real loading state during submission')

// ---- Plan bullets: exactly the frozen 3-per-tier marketing copy ----------
assert.ok(source.includes("FREE: ['扫码点单与菜单', '订单与微信收款', '长期免费']"))
assert.ok(source.includes("STANDARD: ['后厨自动出票', '多员工协同', '智能菜单工具']"))
assert.ok(source.includes("PRO: ['会员积分体系', '优惠券与自动营销', '渠道拉新与分销']"))
for (const forbidden of ['自定义积分', '自定义等级', '营销活动搭建', '一键群发', 'Campaign Builder']) {
  assert.ok(!source.includes(forbidden), `must not market unverified capability: ${forbidden}`)
}

console.log('test-subscription-page-wiring: ok')
