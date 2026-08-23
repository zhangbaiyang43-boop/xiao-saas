import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

describe('P0-09 customer financial attention', () => {
  it('shows late-paid cancelled orders as refund-required without claiming refund success', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const source = fs.readFileSync(path.resolve(here, '../OrderHistorySheet.vue'), 'utf8')

    expect(source).toContain('v-if="currentTableOrder.refundRequired"')
    expect(source).toContain('订单已取消，付款已成功，请联系商家处理退款')
    expect(source).toContain('请保留订单信息并联系商家处理退款。')
    expect(source).not.toContain('系统不会自动退款')
    expect(source).not.toContain('退款成功')
  })
})
