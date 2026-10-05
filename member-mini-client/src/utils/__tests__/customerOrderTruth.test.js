import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { formatOrderStatusText, ORDER_STATUS_TEXT } from '@/utils/orderStatus'
import { successText } from '@/subpkg-order/utils/orderText.js'

const readSource = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8')
const BANNED = /等待接单|待接单|正在确认订单|已上餐/

describe('customer order wording only states facts the system knows', () => {
  it('pending is no longer "waiting to be accepted" on the payment success sheet', () => {
    expect(successText.statusPending).toBe('订单已提交')
    for (const text of Object.values(successText)) {
      if (typeof text === 'string') expect(text).not.toMatch(BANNED)
    }
  })

  it('the shared fallback labels never claim acceptance or serving', () => {
    expect(ORDER_STATUS_TEXT.pending).toBe('订单已提交')
    expect(ORDER_STATUS_TEXT.done).toBe('厨房已出餐')
    for (const text of Object.values(ORDER_STATUS_TEXT)) expect(text).not.toMatch(BANNED)
  })

  it('server-derived kitchen wording wins over the fallback label', () => {
    expect(formatOrderStatusText('pending', '订单已发送至厨房')).toBe('订单已发送至厨房')
    expect(formatOrderStatusText('pending', '订单已提交')).toBe('订单已提交')
    expect(formatOrderStatusText('done', '厨房已出餐')).toBe('厨房已出餐')
  })

  it('legacy workbench states keep their real wording', () => {
    expect(formatOrderStatusText('preparing')).toBe('制作中')
    expect(successText.statusPreparing).toBe('商家已接单，正在制作')
    expect(formatOrderStatusText('pending_payment')).toBe('待支付')
  })

  it('the table bill view no longer says the merchant is confirming or that food was served', () => {
    const source = readSource('../../subpkg-order/composables/useTableBillView.js')
    expect(source).not.toContain('商家正在确认订单')
    expect(source).not.toContain('餐品已上餐')
    expect(source).toContain("pending: '订单已提交'")
    expect(source).toContain("done: '厨房已出餐，请留意'")
    // real workbench-mode wording stays
    expect(source).toContain("preparing: '商家已接单，正在制作'")
  })

  it('M4: pending -> preparing no longer toasts or vibrates; terminal events still do', () => {
    const source = readSource('../../subpkg-order/composables/useOrderStatusPoll.js')
    expect(source).not.toContain('merchantAccepted')
    expect(source).not.toMatch(/newVal === 'preparing'/)
    expect(source).toContain("newVal === 'done'")
    expect(source).toContain("newVal === 'rejected'")
  })

  it('done is never described as food fully served', () => {
    const source = readSource('../../subpkg-order/composables/useTableBillView.js')
    expect(source).not.toContain("title: '菜品已上齐'")
    expect(source).toContain("title: '厨房已出餐'")
  })
})
