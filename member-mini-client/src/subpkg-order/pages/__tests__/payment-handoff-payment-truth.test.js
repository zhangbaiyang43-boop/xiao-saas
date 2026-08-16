import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('../payment-handoff.vue', import.meta.url)),
  'utf8',
)

const handlePayStart = source.indexOf('async handlePay()')
const handlePay = source.slice(handlePayStart, source.indexOf('\n    },', handlePayStart) + 7)

describe('payment handoff server-truth contract (P0-06 H01-H04)', () => {
  it('H01 does not mark paid from requestPayment SDK success alone', () => {
    expect(handlePayStart).toBeGreaterThan(-1)
    expect(handlePay).not.toMatch(/await uni\.requestPayment\([\s\S]*?\)\s*this\.paid = true/)
  })

  it('H02 polls the server and marks paid only from a paid server result', () => {
    expect(source).toContain('waitForServerPaymentConfirmation')
    expect(handlePay).toMatch(/const confirmed = await this\.waitForServerPaymentConfirmation\(\)/)
    expect(handlePay).toMatch(/this\.paid = confirmed/)
  })

  it('H03 keeps cancellation retryable without starting server confirmation polling', () => {
    expect(handlePay).toMatch(/errMsg\?\.includes\('cancel'\)/)
    expect(source).toContain("return { paid: false, reason: 'cancelled' }")
  })

  it('H04 leaves timeout pending and retryable instead of showing payment success', () => {
    expect(source).toContain("throw new Error('支付结果确认中，请稍后重试')")
    expect(source).toMatch(/data\?\.status === 'PAID' \|\| data\?\.payment_status === 'paid'/)
  })
})
