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

  it('tells empty-list users there are no orders and they can go order', () => {
    expect(orders).toContain('title="暂无订单"')
    expect(orders).toContain('desc="在本店完成点餐后，历史订单会显示在这里。"')
    expect(orders).toContain('action-text="去点餐"')
    expect(orders).toContain('@action="goOrder"')
    expect(orders).not.toContain('登录后在本店点餐')
    expect(orders).not.toContain('登录后可查看本店历史订单状态')
  })
})
