import assert from 'node:assert/strict'
import { formatMoney, merchantNetEarnedText } from '../src/utils/money.js'
import { leadStatusText, ledgerStatusText, signedLedgerAmount } from '../src/utils/status.js'
import { createDashboardPoller } from '../src/utils/polling.js'
import { sanitizeSelfParams } from '../src/utils/selfScope.js'
import { appendPageItems } from '../src/utils/pagination.js'
import { buildMerchantNameMapFromBindings, enrichCommissions } from '../src/utils/commissionEnrich.js'

assert.equal(formatMoney(11980), '¥119.80')
assert.equal(formatMoney(0), '¥0.00')
assert.equal(formatMoney(-11980), '-¥119.80')
assert.equal(merchantNetEarnedText(11980), '已产生收益 ¥119.80')
assert.equal(merchantNetEarnedText(0), '暂未产生收益')
assert.equal(merchantNetEarnedText(-3000), '当前净收益 -¥30.00')
assert.equal(signedLedgerAmount({ entry_type: 'EARN', commission_amount_cents: 11980 }), '+¥119.80')
assert.equal(signedLedgerAmount({ entry_type: 'REVERSAL', commission_amount_cents: -11980 }), '-¥119.80')
assert.equal(ledgerStatusText('PENDING'), '待结算')
assert.equal(ledgerStatusText('AVAILABLE'), '可结算')
assert.equal(ledgerStatusText('SETTLED'), '已结算')
assert.equal(leadStatusText('PROTECTED'), '已报备')

const sanitized = sanitizeSelfParams({ page: 1, page_size: 20, partner_id: 123 })
assert.deepEqual(sanitized, { page: 1, page_size: 20 })

const merged = appendPageItems([{ id: '1' }], [{ id: '1' }, { id: '2' }])
assert.deepEqual(merged, [{ id: '1' }, { id: '2' }])

const merchantNameMap = buildMerchantNameMapFromBindings(
  [{ tenant_id: 'tenant-a', merchant_display_name: '?????', source_lead_id: 'lead-a' }],
  [{ id: 'lead-a', merchant_name: '老王川菜馆' }],
)
assert.equal(enrichCommissions([{ id: '1', tenant_id: 'tenant-a' }], merchantNameMap)[0].merchant_display_name, '老王川菜馆')

let inFlight = 0
let maxInFlight = 0
const poller = createDashboardPoller({
  intervalMs: 1,
  fetchDashboard: async () => {
    inFlight += 1
    maxInFlight = Math.max(maxInFlight, inFlight)
    await new Promise((resolve) => setTimeout(resolve, 5))
    inFlight -= 1
    return { latest_commissions: [{ id: '100', entry_type: 'EARN', commission_amount_cents: 11980 }] }
  },
  onData: () => {},
  onNewEarn: () => {},
})
const a = poller.refreshNow()
const b = poller.refreshNow()
await Promise.all([a, b])
poller.stop()
assert.equal(maxInFlight, 1)

let feedback = 0
let feedbackRefreshes = 0
const feedbackPoller = createDashboardPoller({
  intervalMs: 10,
  fetchDashboard: async () => {
    feedbackRefreshes += 1
    return { latest_commissions: [{ id: String(100 + feedbackRefreshes), entry_type: 'EARN', commission_amount_cents: 11980 }] }
  },
  onData: () => {},
  onNewEarn: () => { feedback += 1 },
})
await feedbackPoller.refreshNow()
assert.equal(feedback, 0)
await feedbackPoller.refreshNow()
feedbackPoller.stop()
assert.equal(feedback, 1)

console.log('CHANNEL_PORTAL_TEST_OK')
