/**
 * Payment handoff polling contract checks.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = fs.readFileSync(path.join(root, 'src/components/AssistedOrderSheet.vue'), 'utf8')

function countText(text) {
  return source.split(text).length - 1
}

assert.equal(countText('setInterval('), 0, 'Payment handoff polling must not use setInterval')
assert.ok(source.includes('setTimeout('), 'Payment handoff polling must use chained setTimeout')
assert.ok(source.includes('clearTimeout('), 'Payment handoff polling must clear timeout handles')
assert.ok(source.includes('paymentStatusInFlight'), 'Payment handoff polling must have an in-flight guard')
assert.ok(source.includes('checkPaymentHandoffStatus'), 'Payment handoff status checks must use one entry point')
assert.ok(source.includes('schedulePaymentStatusCheck'), 'Payment handoff polling must use one scheduler')
assert.ok(source.includes('clearPaymentStatusTimer'), 'Payment handoff polling must use one clear helper')
assert.ok(source.includes('document.hidden'), 'Payment handoff polling must pause while hidden')
assert.ok(source.includes('visibilitychange'), 'Payment handoff polling must listen for visibility changes')
assert.ok(source.includes("addEventListener('visibilitychange'"), 'Visibility listener must be registered')
assert.ok(source.includes("removeEventListener('visibilitychange'"), 'Visibility listener must be removed')
assert.ok(source.includes('PAID'), 'Payment handoff polling must handle PAID')
assert.ok(source.includes('EXPIRED'), 'Payment handoff polling must handle EXPIRED')
assert.ok(source.includes('CANCELLED'), 'Payment handoff polling must handle CANCELLED')
assert.ok(source.includes('CLAIMED'), 'Payment handoff polling must continue CLAIMED')
assert.ok(source.includes('PENDING_SCAN'), 'Payment handoff polling must continue PENDING_SCAN')
assert.ok(source.includes('isHandoffTerminal'), 'Payment handoff polling must centralize terminal checks')
assert.ok(source.includes('shouldPollPaymentHandoff'), 'Payment handoff polling must centralize poll eligibility')

console.log('test-payment-handoff-polling: ok')
