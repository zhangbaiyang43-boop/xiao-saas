/**
 * Merchant Self-Serve Onboarding Completion.
 *
 * Activation Home was previously just a navigation directory: clicking a
 * step took the merchant to the real business page, but nothing ever led
 * them back or re-evaluated completion -- they had to find their own way
 * back and manually refresh. This proves the task -> completion -> next-step
 * loop exists, that it never touches backend/business contracts (activation-
 * status stays a pure-facts endpoint, no onboarding_step/progress fields),
 * and that normal (non-onboarding) navigation into /menu and /entrance-codes
 * is completely unaffected.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const activationHome = fs.readFileSync(path.join(root, 'src/views/ActivationHome.vue'), 'utf8')
const menuManage = fs.readFileSync(path.join(root, 'src/views/MenuManage.vue'), 'utf8')
const entranceCodeList = fs.readFileSync(path.join(root, 'src/views/EntranceCodeList.vue'), 'utf8')
const tenantContract = fs.readFileSync(path.join(root, '..', 'saas-base/app/api/v1/tenant.py'), 'utf8')

// ---- Navigation contract: single consistent onboarding query param -------
assert.ok(activationHome.includes("router.push('/menu?onboarding=1')"), 'Step 1 must navigate with ?onboarding=1')
assert.ok(activationHome.includes("router.push('/entrance-codes?onboarding=1')"), 'Step 2 must navigate with ?onboarding=1')
assert.ok(!activationHome.includes('localStorage'), 'onboarding progress must never be persisted via localStorage')

// ---- CASE A / CASE B: MenuManage onboarding vs normal ---------------------
assert.ok(menuManage.includes("route.query.onboarding === '1'"), 'MenuManage must read onboarding from the URL query, not a stored flag')
assert.ok(menuManage.includes('function maybeCompleteOnboardingStep1'), 'must define a small, reusable step-1 completion check')
{
  const fnStart = menuManage.indexOf('function maybeCompleteOnboardingStep1')
  const fnEnd = menuManage.indexOf('\n}', fnStart)
  const fnBody = menuManage.slice(fnStart, fnEnd)
  assert.ok(fnBody.includes('isOnboarding.value'), 'completion check must be gated on onboarding mode')
  assert.ok(fnBody.includes('availableCount.value > 0'), 'completion must be based on a real available dish existing, not a fabricated flag')
  assert.ok(fnBody.includes("router.replace('/activation')"), 'completion must return to Activation Home via replace (no dead-end back button into a finished step)')
}
// Not just createMenuItem -- re-shelving an existing dish must also be able to complete Step 1.
assert.ok(menuManage.includes('maybeCompleteOnboardingStep1()'), 'completion check must actually be called somewhere')
{
  const callSites = menuManage.split('maybeCompleteOnboardingStep1()').length - 1
  assert.ok(callSites >= 3, `expected maybeCompleteOnboardingStep1() to be wired into saveDish + toggleCategory + restoreAll (found ${callSites} call sites)`)
}
assert.ok(menuManage.includes('if (form.shareToLibrary'), 'existing createMenuItem/library-share business logic must be untouched')
assert.ok(!menuManage.includes('onboarding_step'), 'must not introduce a persisted onboarding_step field')
assert.ok(!menuManage.includes('onboarding_completed'), 'must not introduce a persisted onboarding_completed field')
// CASE B: normal-mode load path is still an unconditional, un-gated loadMenu() call.
{
  const mountStart = menuManage.indexOf('onMounted(() => {')
  const mountEnd = menuManage.indexOf('\n})', mountStart)
  const mountBody = menuManage.slice(mountStart, mountEnd)
  assert.ok(/}\s*else\s*{\s*loadMenu\(\)\s*}/.test(mountBody), 'normal (non-onboarding) mount must still call loadMenu() unconditionally, with no auto-redirect/auto-open')
}

// ---- CASE C / CASE D: EntranceCodeList onboarding vs normal ---------------
assert.ok(entranceCodeList.includes("route.query.onboarding === '1'"), 'EntranceCodeList must read onboarding from the URL query')
assert.ok(entranceCodeList.includes('async function checkOnboardingStep2'), 'must define the step-2 completion check')
{
  const fnStart = entranceCodeList.indexOf('async function checkOnboardingStep2')
  const fnEnd = entranceCodeList.indexOf('\n}', fnStart)
  const fnBody = entranceCodeList.slice(fnStart, fnEnd)
  assert.ok(fnBody.includes('getActivationStatus'), 'completion must be decided by the real activation-status fact, not a client-side channel guess')
  assert.ok(fnBody.includes('has_entrance_codes'), 'must check has_entrance_codes specifically')
  assert.ok(fnBody.includes("router.replace('/activation')"), 'completion must return to Activation Home via replace')
}
// Onboarding mode must default to and stay on TABLE -- scene picker hidden, not just visually restricted.
assert.ok(/v-if="!isOnboarding"\s+label="使用场景"/.test(entranceCodeList), 'scene picker (POSTER/DOUYIN) must be hidden entirely in onboarding mode')
assert.ok(entranceCodeList.includes("form.channel = 'TABLE'"), 'openCreate must still default to TABLE (existing default preserved)')
assert.ok(!entranceCodeList.includes('onboarding_step'), 'must not introduce a persisted onboarding_step field')
// CASE D: normal creation message/path untouched.
assert.ok(entranceCodeList.includes("isOnboarding.value ? '桌码已生成' : '已创建'"), 'normal creation must still show the original 已创建 message')

// ---- CASE E / CASE F: Step 3 refresh, no continuous polling ---------------
assert.ok(activationHome.includes('我已下单，检查结果'), 'must offer an explicit manual check button (no silent-only polling)')
assert.ok(activationHome.includes('checkTestOrderResult'), 'manual button must call an explicit check handler')
assert.ok(activationHome.includes("document.addEventListener('visibilitychange'"), 'must refresh once on tab/app regaining visibility')
assert.ok(activationHome.includes("document.removeEventListener('visibilitychange'"), 'visibility listener must be cleaned up on unmount (onBeforeUnmount)')
assert.ok(!/setInterval/.test(activationHome), 'must never poll activation-status on a timer')
assert.ok(!/setInterval/.test(menuManage), 'onboarding must not introduce polling in MenuManage')
assert.ok(!/setInterval/.test(entranceCodeList), 'onboarding must not introduce polling in EntranceCodeList')

// ---- Backend contract left untouched (pure facts, no persisted state) ----
assert.ok(tenantContract.includes('"has_dishes": dish_count > 0'), 'backend activation-status contract must be unchanged')
assert.ok(tenantContract.includes('"has_entrance_codes": entrance_code_count > 0'), 'backend activation-status contract must be unchanged')
assert.ok(!tenantContract.includes('onboarding_step'), 'backend must not gain a persisted onboarding_step column/field')
assert.ok(!tenantContract.includes('onboarding_progress'), 'backend must not gain a persisted onboarding_progress column/field')

console.log('test-onboarding-continuation: ok')
