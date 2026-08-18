/**
 * Phase F1G-CM-B — Merchant manual-verified-payment UX contract checks.
 *
 * Same convention as test-subscription-page-wiring.mjs: no component-render
 * framework exists in this repo, so these are structural / text-presence
 * assertions against the real SubscriptionSettings.vue source, proving the
 * component wires the manual-payment flow correctly and never fakes a
 * payment fact on the frontend. Pure-logic pieces (resolveManualPaymentAvailable,
 * manualPaymentStatusCopy, billingPeriodLabel) are genuinely unit-tested in
 * test-subscription-ui-logic.mjs; this file only checks wiring.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'src/views/settings/SubscriptionSettings.vue'), 'utf8')
const apiSource = fs.readFileSync(path.join(root, 'src/api/index.js'), 'utf8')

function indexOfOrFail(text, label) {
  const i = source.indexOf(text)
  assert.ok(i !== -1, `expected to find: ${label}`)
  return i
}

// ---- manual readiness enables/disables the purchase CTA -------------------
assert.ok(
  source.includes(':disabled="!(onlinePaymentAvailable || manualPaymentAvailable) || purchaseSubmitting"'),
  'purchase CTA must be enabled when either online or manual payment is available',
)
assert.ok(
  source.includes('v-if="!onlinePaymentAvailable && !manualPaymentAvailable"'),
  'the payment-unavailable banner must only show when BOTH online and manual are unavailable',
)

// ---- provider=MANUAL is actually requested, amount is never client-supplied
{
  const providerIdx = indexOfOrFail(
    "const provider = onlinePaymentAvailable.value ? 'WXPAY' : 'MANUAL'",
    'provider selection falling back to MANUAL',
  )
  const createPaymentIdx = indexOfOrFail('await createBillingPayment(invoiceId, { provider })', 'createBillingPayment call using the selected provider')
  assert.ok(providerIdx < createPaymentIdx, 'provider must be resolved before requesting payment creation')
}
assert.ok(!/createBillingPayment\([^)]*amount/i.test(source), 'must never send a client-computed amount when creating a payment')
assert.ok(!/amount_cents\s*[:=]\s*\d/.test(source), 'amount_cents must never be a literal computed on the frontend')

// ---- manual claim call is wired to the real API, with a loading lock ------
assert.ok(apiSource.includes("request.post(`/v1/billing/payments/${paymentId}/manual-claim`)"), 'claimManualBillingPayment must call the real manual-claim endpoint')
assert.ok(source.includes('claimManualBillingPayment'), 'component must import/call claimManualBillingPayment')
{
  const fnIdx = indexOfOrFail('async function handleManualClaim()', 'handleManualClaim function')
  const guardIdx = indexOfOrFail('if (manualClaimSubmitting.value || !manualPayment.value?.id) return', 'reentrancy guard for manual claim')
  assert.ok(fnIdx < guardIdx, 'the reentrancy guard must be inside handleManualClaim')
  assert.ok(source.includes(':loading="manualClaimSubmitting"'), 'claim button must show a real loading state')
}

// ---- CLAIM_AUTHORITY_FREEZE: claim must never locally fake a paid/success
// state -- the frontend must not set payment.status/manual_review_status by
// itself, only read what the server returns. --------------------------------
assert.ok(!/manualPayment\.value\.status\s*=\s*['"]PAID['"]/.test(source), 'frontend must never set payment.status = PAID itself')
assert.ok(!/manual_review_status\s*:\s*['"]WAITING_CONFIRMATION['"]/.test(source), 'frontend must never fabricate manual_review_status locally; it must come from the server response')

// ---- claim success must NOT render "支付成功/付款成功/已开通" -------------
// (that copy is reserved for the real purchaseSuccess modal, only reachable
// via payment.status === 'PAID' coming back from polling, i.e. after a real
// SuperAdmin confirm.)
{
  const claimFnIdx = indexOfOrFail('async function handleManualClaim()', 'handleManualClaim function')
  const nextFnIdx = source.indexOf('\nfunction ', claimFnIdx + 1)
  const claimFnBody = source.slice(claimFnIdx, nextFnIdx === -1 ? undefined : nextFnIdx)
  for (const forbidden of ['支付成功', '付款成功', '专业版已开通', "purchaseSuccess.value = {"]) {
    assert.ok(!claimFnBody.includes(forbidden), `handleManualClaim must not render forbidden success copy/state: ${forbidden}`)
  }
}
// The waiting-state copy itself must never say "支付成功/付款成功/已开通".
{
  const waitingBlockIdx = indexOfOrFail("manual_review_status === 'WAITING_CONFIRMATION'", 'waiting-state template branch')
  const waitingBlockEnd = source.indexOf('</template>', waitingBlockIdx)
  const waitingBlock = source.slice(waitingBlockIdx, waitingBlockEnd)
  for (const forbidden of ['支付成功', '付款成功', '已开通']) {
    assert.ok(!waitingBlock.includes(forbidden), `waiting-state template must not include: ${forbidden}`)
  }
}

// ---- waiting / rejected copy exists, sourced from the shared helper -------
assert.ok(source.includes('manualPaymentStatusCopy'), 'must use the shared frozen-copy helper, not ad-hoc waiting/rejected text')
assert.ok(source.includes("manual_review_status === 'REJECTED'"), 'rejected review status must be handled explicitly')
assert.ok(source.includes('manualStatusCopy.actionText'), 'rejected state must offer the resubmit action from the shared copy helper')

// ---- QR URL is server-driven, never hardcoded / committed ------------------
assert.ok(source.includes(':src="manualPayment.qr_url"'), 'QR image src must come from the server-provided payment record')
assert.ok(!/qr_url\s*:\s*['"]https?:\/\//.test(source), 'must never hardcode a production QR URL literal')
assert.ok(!/data:image\/(png|jpe?g);base64,/.test(source), 'must never embed a base64 QR image in source')
assert.ok(source.includes('@error="onQrError"'), 'QR image load failures must be handled')
assert.ok(source.includes('qrLoadError'), 'QR failure state must disable the claim CTA (Phase 9)')
assert.ok(source.includes(':disabled="qrLoadError"'), 'claim button must be disabled when the QR failed to load')

// ---- payment success (PAID) refreshes subscription + closes manual modal --
{
  const paidIdx = indexOfOrFail("payment.status === 'PAID'", 'PAID branch of payment status handling')
  const refreshIdx = indexOfOrFail('await loadPage()', 'current-subscription refresh on PAID')
  const modalCloseIdx = source.indexOf('manualModalOpen.value = false', paidIdx)
  assert.ok(paidIdx < refreshIdx, 'reaching PAID must trigger a current-subscription refresh')
  assert.ok(modalCloseIdx !== -1 && paidIdx < modalCloseIdx, 'reaching PAID must close the manual payment modal')
}

// ---- manual polling interval is DB-friendly (Phase 15: ~8-10s, not the
// WXPAY handoff's 2.5s), while reusing the exact same polling shape/timer --
{
  const manualIntervalIdx = indexOfOrFail('const MANUAL_PAYMENT_POLL_INTERVAL_MS = 8000', 'manual payment poll interval constant (8-10s range)')
  assert.ok(manualIntervalIdx !== -1)
  assert.ok(
    source.includes('startPaymentPolling(manualPayment.value.id, MANUAL_PAYMENT_POLL_INTERVAL_MS)'),
    'claiming/resubmitting a manual payment must poll at the slower manual interval, not the 2.5s WXPAY cadence',
  )
}

// ---- polling stays read-only and shares the existing cleanup contract -----
assert.ok(source.includes('function mergeManualPayment(payment)'), 'manual payment state must only be updated from real server responses')
assert.ok(source.includes('onBeforeUnmount'), 'manual polling reuses the page-level teardown on unmount')
assert.ok(source.includes('stopBillingPaymentPolling()'), 'rejected review status must stop active polling until resubmit')

// ---- internal technical state must never leak into user-facing copy -------
// (Phase 40 — no raw payment/invoice ids, provider name, or manual_review_status
// enum values shown directly in the template.)
{
  const scriptIdx = indexOfOrFail('<script setup>', 'script setup block')
  const template = source.slice(0, scriptIdx)
  for (const forbidden of ['{{ manualPayment.id }}', '{{ manualPayment.invoice_id }}', '{{ manualPayment.provider }}', '{{ manualPayment.manual_review_status }}']) {
    assert.ok(!template.includes(forbidden), `template must not directly render internal field: ${forbidden}`)
  }
}

console.log('test-subscription-manual-payment: ok')
