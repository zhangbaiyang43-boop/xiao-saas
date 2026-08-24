import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const orders = readFileSync(path.resolve(here, '../orders.vue'), 'utf8')

describe('history order list click feedback', () => {
  it('toasts that dish detail lives on the live table sheet, without opening a detail page', () => {
    expect(orders).toContain('@click="explainNoDetail"')
    expect(orders).toContain("title: '菜品明细请在本桌订单里查看'")
    expect(orders).toContain('uni.showToast')
    expect(orders).not.toContain('/subpkg-member/pages/consumption-detail')
    expect(orders).not.toContain('openOrders=1')
    expect(orders).not.toMatch(/navigateTo\(\{\s*url:\s*['"]\/subpkg-order\/pages\/menu/)
  })
})
