import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

describe('P1-01 mine order entry', () => {
  it('sends 我的订单 to the member order list and keeps 消费记录', () => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    const mine = fs.readFileSync(path.resolve(here, '../mine.vue'), 'utf8')
    const api = fs.readFileSync(path.resolve(here, '../../../api/order.js'), 'utf8')
    expect(mine).toContain("go('/subpkg-member/pages/orders')")
    expect(mine).toContain("go('/subpkg-member/pages/consumptions')")
    expect(mine).toContain('goConsumptions')
    expect(api).toContain('/v1/member/orders')
    expect(api).toContain("url: '/v1/orders/my'")
  })
})
