// 接单提醒 P1/P2/P3 修复：alertEnabled（用户偏好）和 audioNeedsUnlock（浏览器声音
// 引擎是否真正就绪）是两个独立状态，之前只展示前者，导致"提醒开"绿色徽章和"还没
// 生效"黄色横幅同时出现、看起来自相矛盾。仓库没有 Vue render test framework
// （见 test-phase05a 等既有测试的同类说明），这里跟既有惯例一样用真实源码的结构切片
// 验证，不做浏览器运行时渲染断言。
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const orderManageSrc = fs.readFileSync(path.join(root, 'src/views/OrderManage.vue'), 'utf8').replace(/\r\n/g, '\n')
const alertSrc = fs.readFileSync(path.join(root, 'src/composables/useOrderAlert.js'), 'utf8').replace(/\r\n/g, '\n')

const failures = []
function test(name, fn) {
  try {
    fn()
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, error })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}

function slice(startMarker, endMarker) {
  const rest = orderManageSrc.split(startMarker, 2)[1]
  if (rest == null) throw new Error(`marker not found: ${startMarker}`)
  return endMarker ? rest.split(endMarker, 1)[0] : rest
}

// ---------------------------------------------------------------------------
// P1: badge itself reflects the combined state, not just alertEnabled.
// ---------------------------------------------------------------------------

test('P1.1 badge shows plain green "提醒开" only when enabled AND unlocked', () => {
  // Later revision (per explicit product direction: an already-on reminder
  // must never be one-tap-closable from the header) reordered the branches
  // so the pending/needs-unlock case is checked first and the plain "on"
  // indicator is the v-else-if fallback -- that ordering makes it reachable
  // only when alertEnabled is true AND the pending branch's audioNeedsUnlock
  // check already failed, i.e. exactly alertEnabled && !audioNeedsUnlock,
  // without needing to spell out the negation a second time.
  const badgeArea = slice('<div style="display:flex;align-items:center;gap:8px">', '</a-button>\n        <a-button type="text" aria-label="刷新"')
  const pendingIdx = badgeArea.indexOf('v-if="alertEnabled && audioNeedsUnlock"')
  const onIdx = badgeArea.indexOf('v-else-if="alertEnabled"')
  assert.ok(pendingIdx !== -1 && onIdx !== -1 && pendingIdx < onIdx, 'the plain "on" indicator must be a v-else-if chained after the alertEnabled && audioNeedsUnlock pending branch, so it only renders when alertEnabled is true and audioNeedsUnlock is false')
  const greenBlock = badgeArea.slice(onIdx, badgeArea.indexOf('a-button', onIdx))
  assert.ok(greenBlock.includes('class="alert-on-indicator"'), 'the alertEnabled && !audioNeedsUnlock branch must render the plain indicator')
  assert.ok(!greenBlock.includes('@click'), 'an already-on reminder must not be clickable/closable from this header badge')
})

test('P1.2 badge shows an amber pending state when enabled but not yet unlocked, and clicking it unlocks', () => {
  const badgeArea = slice('<div style="display:flex;align-items:center;gap:8px">', '</a-button>\n        <a-button type="text" aria-label="刷新"')
  assert.ok(badgeArea.includes('v-if="alertEnabled && audioNeedsUnlock"'), 'pending badge branch must gate on alertEnabled && audioNeedsUnlock')
  assert.ok(badgeArea.includes('class="alert-pending-badge tap-shrink"'), 'pending badge must use its own distinct class, not reuse alert-on-indicator')
  assert.ok(badgeArea.includes('提醒开 · 待解锁'), 'pending badge text must say "待解锁", not claim full success')
  const pendingBlock = badgeArea.slice(badgeArea.indexOf('alert-pending-badge'), badgeArea.indexOf('提醒开 · 待解锁'))
  assert.ok(pendingBlock.includes('@click="unlockAudio"'), 'clicking the pending badge must call unlockAudio, not disableAlert')
})

test('P1.3 the standalone unlock banner still exists (additive, not replaced)', () => {
  assert.ok(orderManageSrc.includes('unlock-audio-banner'), 'the full-width banner is still a valid, more discoverable entry point')
})

test('P1.4 pending badge reuses the existing amber palette, not a new color', () => {
  const css = slice('.alert-pending-badge {', '}')
  assert.ok(css.includes('#b45309') && css.includes('#fffbeb') && css.includes('#fde68a'), 'must reuse the same amber vocabulary as .unlock-audio-banner')
})

// ---------------------------------------------------------------------------
// P2: a failed alert attempt surfaces an active toast, not just a passive flag.
// ---------------------------------------------------------------------------

test('P2.1 playNewOrderBeep reports broken audio through a shared helper on every failure path', () => {
  const fnBody = alertSrc.slice(alertSrc.indexOf('function playNewOrderBeep'), alertSrc.indexOf('function enableAlert'))
  const reportCalls = fnBody.match(/_reportAudioBroken\(\)/g) || []
  assert.equal(reportCalls.length, 2, 'both the still-suspended-after-resume branch and the catch branch must call _reportAudioBroken')
  assert.ok(!fnBody.includes('audioNeedsUnlock.value = true'), 'failure paths must go through _reportAudioBroken, not set the flag directly (that would skip the toast)')
})

test('P2.2 the broken-audio toast is edge-triggered, not fired on every new order while still broken', () => {
  const fnBody = alertSrc.slice(alertSrc.indexOf('function _reportAudioBroken'), alertSrc.indexOf('function playNewOrderBeep'))
  assert.ok(/if \(!audioNeedsUnlock\.value\) \{\s*\n\s*message\.warning/.test(fnBody), 'must only toast when transitioning from working to broken, not every time a new order arrives while already broken')
})

// ---------------------------------------------------------------------------
// P3: unlockAudio must verify resume() actually succeeded before claiming success.
// ---------------------------------------------------------------------------

test('P3.1 unlockAudio is async and awaits resume()', () => {
  const fnBody = alertSrc.slice(alertSrc.indexOf('async function unlockAudio'), alertSrc.indexOf('function ensureAlertProbed'))
  assert.ok(fnBody.includes('await audioCtx.resume()'), 'must await the resume Promise instead of firing it and moving on')
})

test('P3.2 unlockAudio checks the post-resume state before declaring success', () => {
  const fnBody = alertSrc.slice(alertSrc.indexOf('async function unlockAudio'), alertSrc.indexOf('function ensureAlertProbed'))
  const stillSuspendedIdx = fnBody.indexOf("audioCtx.state === 'suspended'")
  const successIdx = fnBody.indexOf('提醒已解锁')
  assert.ok(stillSuspendedIdx !== -1, 'must check audioCtx.state after awaiting resume()')
  assert.ok(successIdx !== -1 && stillSuspendedIdx < successIdx, 'the suspended-check must come before the success toast, not after')
})

test('P3.3 unlockAudio does not clear audioNeedsUnlock or claim success on the still-suspended path', () => {
  const fnBody = alertSrc.slice(alertSrc.indexOf('async function unlockAudio'), alertSrc.indexOf('function ensureAlertProbed'))
  const guardBlock = fnBody.slice(fnBody.indexOf("audioCtx.state === 'suspended'"), fnBody.indexOf("audioCtx.state === 'suspended'") + 120)
  assert.ok(guardBlock.includes('解锁失败'), 'the still-suspended branch must show a failure message')
  assert.ok(!guardBlock.includes('audioNeedsUnlock.value = false'), 'must not clear the flag before confirming success')
})

console.log(`Order alert audio unlock P1/P2/P3: ${failures.length === 0 ? 'passed' : 'FAILED'}`)
if (failures.length > 0) process.exit(1)
