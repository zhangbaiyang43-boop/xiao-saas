/** Phase 05A frontend source contracts. Authored for CI, not executed locally. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const superAdmin = readFileSync(new URL('../src/views/SuperAdmin.vue', import.meta.url), 'utf8')
const panel = readFileSync(new URL('../src/views/super/SubscriptionAdjustmentModal.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/superSubscriptionAdjustments.js', import.meta.url), 'utf8')

assert.match(superAdmin, /SubscriptionAdjustmentModal/)
assert.match(superAdmin, /detail\.subscription_adjustment/)
assert.match(superAdmin, /@committed="refreshDetailAfterAdjustment"/)
assert.match(superAdmin, /natural_expiry_recovery/)

assert.match(api, /subscription-adjustments\/preview/)
assert.match(api, /listSubscriptionAdjustments/)
assert.match(api, /commitSubscriptionAdjustment/)
assert.match(api, /import superRequest from '\.\/superRequest'/)
assert.doesNotMatch(api, /after_expiry\s*:/)
assert.doesNotMatch(api, /^import axios from ['"]axios['"]/m)

for (const preset of ['7', '30', '90', '365']) assert.match(panel, new RegExp(`\\[7, 30, 90, 365\\]|${preset}`))
for (const type of ['GIFT', 'COMPENSATION', 'TRIAL_EXTENSION', 'CORRECTION', 'INTERNAL_TEST', 'OTHER']) {
  assert.match(panel, new RegExp(type))
}
assert.match(panel, /恢复并延长/)
assert.match(panel, /只能延后，不能缩短或保持不变/)
assert.match(panel, /expected_subscription_id: preview\.value\.subscription_id/)
assert.match(panel, /expected_before_expiry: preview\.value\.before_expiry/)
assert.match(panel, /if \(!idempotencyKey\.value\) idempotencyKey\.value = makeUuid\(\)/)
assert.match(panel, /definiteFailureStatuses = \[401, 403, 404, 409, 422\]/)
assert.doesNotMatch(panel, /status >= 400 && status < 500/)
assert.match(panel, /A 5xx\/gateway response can arrive after the DB commit succeeded/)
assert.match(panel, /window\.confirm\(warning\)/)
assert.match(panel, /await loadHistory\(\)/)
assert.doesNotMatch(panel, /ends_at\s*=/)
assert.doesNotMatch(panel, /trial_ends_at\s*=/)
assert.doesNotMatch(panel, /setInterval\(/)
assert.doesNotMatch(panel, /Payment|Invoice|amount_cents|price_month_cents/)

console.log('TEST-FE superSubscriptionAdjustments: passed')
