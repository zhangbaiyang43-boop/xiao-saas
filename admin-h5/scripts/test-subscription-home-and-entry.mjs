/**
 * Phase F1E-B — Home status strip, Settings entry, and router wiring.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dashboard = fs.readFileSync(path.join(root, 'src/views/Dashboard.vue'), 'utf8')
const settings = fs.readFileSync(path.join(root, 'src/views/MerchantSettings.vue'), 'utf8')
const router = fs.readFileSync(path.join(root, 'src/router/index.js'), 'utf8')

// ---- HOME_FAILURE_DOES_NOT_BREAK_DASHBOARD_TEST --------------------------
{
  const fnStart = dashboard.indexOf('async function loadSubscriptionStrip()')
  assert.ok(fnStart !== -1, 'Dashboard must define loadSubscriptionStrip')
  const fnEnd = dashboard.indexOf('\n}', fnStart)
  const fnBody = dashboard.slice(fnStart, fnEnd)
  assert.ok(fnBody.includes('try {'), 'subscription strip load must be wrapped in try/catch')
  assert.ok(fnBody.includes('catch'), 'subscription strip load must catch its own errors')
  assert.ok(fnBody.includes('subscriptionStrip.value = null'), 'a failed load must clear the strip, not leave stale/broken state')
  assert.ok(!fnBody.includes('throw'), 'subscription strip load must never rethrow into the caller')
  assert.ok(!/message\.error/.test(fnBody), 'a failed subscription strip load must stay silent, not interrupt the merchant with a toast')
}
// The strip is rendered behind a v-if guard, so a null value simply doesn't render.
assert.ok(dashboard.includes('v-if="subscriptionStrip"'), 'subscription strip must be conditionally rendered, never assumed present')

// ---- Home strip: read-only, no plans/readiness fetched on the dashboard ---
assert.ok(dashboard.includes('getCurrentSubscription'), 'home strip must use GET /subscription/current')
assert.ok(!dashboard.includes('getSubscriptionPlans'), 'home page must not fetch the plan catalog')
assert.ok(!dashboard.includes('getPaymentReadiness'), 'home page must not fetch payment readiness')

// ---- Home strip never creates an invoice directly -------------------------
assert.ok(!dashboard.includes('createRenewalOrder'), 'home strip must only navigate to /subscription, never create an invoice itself')
assert.ok(dashboard.includes("router.push('/subscription')"), 'home strip click must navigate to the dedicated subscription page')

// ---- Settings entry: navigation only, no duplicated purchase flow --------
assert.ok(settings.includes("router.push('/subscription')"), 'settings must have a 我的套餐 entry navigating to /subscription')
assert.ok(settings.includes('我的套餐'), 'settings entry label must be 我的套餐')
assert.ok(!settings.includes('createRenewalOrder'), 'settings page must not duplicate the purchase flow')
assert.ok(!settings.includes('getSubscriptionPlans'), 'settings page must not render its own plan selector')

// ---- Router: single registration, owner-only, no duplicate prefix --------
assert.ok(router.includes("path: 'subscription', name: 'SubscriptionSettings'"), 'router must register the subscription route')
assert.equal(
  router.split("name: 'SubscriptionSettings'").length - 1, 1,
  'the subscription route must be registered exactly once',
)
{
  const routeLineStart = router.indexOf("path: 'subscription', name: 'SubscriptionSettings'")
  const routeLineEnd = router.indexOf('\n', routeLineStart)
  const routeLine = router.slice(routeLineStart, routeLineEnd)
  assert.ok(routeLine.includes('meta: ownerOnly'), 'subscription route must be owner-only, consistent with billing being an owner concern')
}
// Must not collide with the SuperAdmin surface.
assert.ok(!router.includes("path: '/subscription'"), 'must be registered as a child route, not a top-level path bypassing the auth guard')

console.log('test-subscription-home-and-entry: ok')
