/**
 * Phase F1G-CM-C — SuperAdmin manual-payment verification UX contract checks.
 *
 * Same convention as test-super-channel-partners.mjs: no component-render
 * framework exists in this repo, so these are source-text/regex assertions
 * against the real files, proving the wiring is correct without guessing at
 * runtime behavior. Business authority freeze: this UI is a thin client over
 * the CM-A backend (list/confirm/reject) -- it must never mutate a purchase
 * snapshot (amount/plan/tenant/dates) itself.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const panel = readFileSync(new URL('../src/views/super/ManualPaymentPanel.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/superBilling.js', import.meta.url), 'utf8')

// ---- SuperAdmin.vue wiring: new tab, new panel, existing auth pattern ----
assert.match(superAdmin, /ManualPaymentPanel/)
assert.match(superAdmin, /activeTab === 'billing'/)
assert.match(superAdmin, /待确认付款/)
assert.match(superAdmin, /const activeTab = ref\('merchants'\)/)
assert.match(superAdmin, /let superToken = ''/)
assert.doesNotMatch(superAdmin, /localStorage\.setItem\(['"]superToken/)

// ---- API client: real CM-A endpoints, real auth header, no localStorage --
assert.match(api, /\/super\/billing/)
assert.match(api, /manual-payments/)
assert.match(api, /\/confirm/)
assert.match(api, /\/reject/)
assert.match(api, /'X-Super-Token': superToken/)
assert.doesNotMatch(api, /localStorage/)

// ---- Phase F1G-CM-RF: unified API-origin authority, no raw axios ----------
// superBilling.js must go through the shared superRequest client (which
// resolves the SAME origin as the merchant client via resolveApiBaseURL()),
// never the bare axios package with a browser-relative path -- that's
// exactly the drift that forced a temporary Vite dev-proxy in CM-C/CM-D.
assert.match(api, /import superRequest from '\.\/superRequest'/)
assert.doesNotMatch(api, /^import axios from ['"]axios['"]/m, 'must not import raw axios directly')
assert.doesNotMatch(api, /axios\.(get|post|put|patch|delete)\(/, 'must call through superRequest, not raw axios')
assert.doesNotMatch(api, /['"`]\/api\/super/, 'BASE must not hardcode the /api prefix a second time -- that authority lives in superRequest\'s baseURL')

// ---- PENDING_LIST_WIRED / CONFIRM_WIRED / REJECT_WIRED --------------------
assert.match(panel, /listManualPayments/)
assert.match(panel, /confirmManualPayment/)
assert.match(panel, /rejectManualPayment/)

// ---- Card fields: tenant_name, plan/period, amount, out_trade_no, time ---
assert.match(panel, /item\.tenant_name/)
assert.match(panel, /item\.out_trade_no/)
assert.match(panel, /item\.manual_claimed_at/)
assert.match(panel, /planDisplayName\(item\.plan_code\)/)
assert.match(panel, /item\.billing_period/)

// ---- AMOUNT_AUTHORITY=BACKEND: formatting only, never recomputed ---------
assert.match(panel, /formatYuan\(item\.amount_cents\)/)
assert.doesNotMatch(panel, /amount_cents\s*[*/]/, 'must never multiply/divide amount_cents on the frontend')
assert.doesNotMatch(panel, /price_month_cents|price_year_cents/, 'must never re-derive amount from a plan price table')

// ---- No purchase-snapshot input fields exist (Phase 25) -------------------
for (const forbidden of ['type="number"', 'v-model.*amount', 'ends_at', 'paid_at', 'tenant_id.*select', '<select']) {
  assert.doesNotMatch(panel, new RegExp(forbidden), `must not contain a purchase-snapshot input: ${forbidden}`)
}

// ---- CONFIRM_SECOND_CONFIRMATION_TEST: confirm is gated behind a real
// confirmation dialog showing the money context, not a bare API call -------
{
  const fnIdx = panel.indexOf('function handleConfirmClick(item)')
  assert.ok(fnIdx !== -1, 'expected handleConfirmClick')
  const confirmCallIdx = panel.indexOf('window.confirm(', fnIdx)
  const doConfirmIdx = panel.indexOf('doConfirm(item)', fnIdx)
  assert.ok(confirmCallIdx !== -1 && confirmCallIdx < doConfirmIdx, 'confirm must show window.confirm before calling doConfirm')
}
assert.match(panel, /确认已到账/)
assert.match(panel, /请确认已经在实际收款账户中看到这笔款项/)
// The confirm dialog title must be about money arriving, not about the plan.
assert.doesNotMatch(panel, /确认开通套餐/)

// ---- REJECT_SECOND_CONFIRMATION_TEST --------------------------------------
{
  const fnIdx = panel.indexOf('function handleRejectClick(item)')
  assert.ok(fnIdx !== -1, 'expected handleRejectClick')
  const confirmCallIdx = panel.indexOf('window.confirm(', fnIdx)
  const doRejectIdx = panel.indexOf('doReject(item, note)', fnIdx)
  assert.ok(confirmCallIdx !== -1 && confirmCallIdx < doRejectIdx, 'reject must show window.confirm before calling doReject')
}
assert.match(panel, /暂未查到到账/)
assert.match(panel, /暂未查到对应款项/)
// Reject must not use failure/error copy the merchant already sees.
assert.doesNotMatch(panel, /订单失败|支付失败/)

// ---- CONFIRM_PAYLOAD contains no purchase-snapshot fields (Phase 7/24) ---
{
  const start = api.indexOf('export async function confirmManualPayment')
  const end = api.indexOf('export async function rejectManualPayment')
  const body = api.slice(start, end)
  for (const forbidden of ['amount', 'tenant_id', 'plan_code', 'billing_period', 'ends_at', 'paid_at']) {
    assert.ok(!body.includes(forbidden), `confirmManualPayment payload must not include: ${forbidden}`)
  }
  assert.match(body, /\{\s*note:\s*note \|\| undefined\s*\}/, 'confirm body must be exactly { note }')
}

// ---- DIRECT_SUBSCRIPTION_MUTATION=NO: no subscription/entitlement API ----
for (const forbidden of ['subscription/extend', 'subscription/update', '/plan-override', 'ends_at =', 'SubscriptionService', 'apply_paid_purchase']) {
  assert.ok(!panel.includes(forbidden), `panel must not directly mutate subscription state: ${forbidden}`)
  assert.ok(!api.includes(forbidden), `api client must not directly mutate subscription state: ${forbidden}`)
}

// ---- CONFIRM_SUCCESS refetches the authoritative list, no local fake-paid
{
  const doConfirmIdx = panel.indexOf('async function doConfirm(item)')
  const nextFnIdx = panel.indexOf('\nasync function ', doConfirmIdx + 1)
  const body = panel.slice(doConfirmIdx, nextFnIdx === -1 ? undefined : nextFnIdx)
  assert.ok(body.includes('await loadPayments()'), 'confirm success must refetch the authoritative pending list')
  assert.ok(!body.includes("item.review_status = 'CONFIRMED'"), 'must not locally fake the review status as confirmed')
}
assert.match(panel, /已确认到账，套餐已自动开通/)
assert.doesNotMatch(panel, /套餐已手动延长/)

// ---- Concurrent-superadmin stale state: friendly copy, not "系统异常" ----
assert.match(panel, /该付款状态已更新/)
assert.doesNotMatch(panel, /系统异常/)

// ---- Empty state exists, stays minimal -------------------------------------
assert.match(panel, /暂无待确认付款/)

// ---- Loading lock: per-card, not a whole-page lock ------------------------
assert.match(panel, /confirmingId/)
assert.match(panel, /rejectingId/)
assert.match(panel, /function isBusy\(item\)/)

// ---- No high-frequency SuperAdmin polling (Phase 15) -----------------------
assert.doesNotMatch(panel, /setInterval\(/)
for (const forbidden of ['2500', '2000)']) {
  assert.ok(!panel.includes(forbidden), `must not poll at WXPAY/manual-claim frequency: ${forbidden}`)
}

console.log('TEST-FE superManualPayments: passed')
