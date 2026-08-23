import { describe, expect, it } from 'vitest'
import { formatOrderStatusText, UNKNOWN_ORDER_STATUS_TEXT } from '@/utils/orderStatus'

describe('formatOrderStatusText', () => {
  it('does not render pending_payment token', () => {
    expect(formatOrderStatusText('pending_payment')).toBe('待支付')
    expect(formatOrderStatusText('pending_payment')).not.toBe('pending_payment')
  })

  it('covers fulfillment statuses', () => {
    expect(formatOrderStatusText('pending')).toBe('待接单')
    expect(formatOrderStatusText('preparing')).toBe('制作中')
    expect(formatOrderStatusText('done')).toBe('已上餐')
    expect(formatOrderStatusText('settled')).toBe('已结账')
    expect(formatOrderStatusText('cancelled')).toBe('已取消')
    expect(formatOrderStatusText('rejected')).toBe('已拒单')
  })

  it('unknown status is Chinese, not the English token', () => {
    expect(formatOrderStatusText('weird_token')).toBe(UNKNOWN_ORDER_STATUS_TEXT)
    expect(formatOrderStatusText('weird_token')).not.toMatch(/^[A-Za-z0-9_]+$/)
    expect(formatOrderStatusText('pending', 'pending')).toBe('待接单')
  })
})
