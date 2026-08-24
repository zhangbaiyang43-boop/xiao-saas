import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

describe('P1-01 mine order entry', () => {
  const here = path.dirname(fileURLToPath(import.meta.url))
  const mine = fs.readFileSync(path.resolve(here, '../mine.vue'), 'utf8')
  const orderText = fs.readFileSync(
    path.resolve(here, '../../../subpkg-order/utils/orderText.js'),
    'utf8',
  )
  const api = fs.readFileSync(path.resolve(here, '../../../api/order.js'), 'utf8')

  it('sends 我的订单 to the member order list and keeps 消费记录', () => {
    expect(mine).toContain("go('/subpkg-member/pages/orders')")
    expect(mine).toContain("go('/subpkg-member/pages/consumptions')")
    expect(mine).toContain('goConsumptions')
    expect(api).toContain('/v1/member/orders')
    expect(api).toContain("url: '/v1/orders/my'")
  })

  it('sends the recent-order card to the history list, not menu?openOrders=1', () => {
    expect(mine).toContain('class="recent-order-card" @click="goOrders"')
    expect(mine).not.toContain('openRecentOrder')
    const cardBlock = mine.slice(
      mine.indexOf('class="recent-order-card"'),
      mine.indexOf('class="service-card"'),
    )
    expect(cardBlock).not.toContain('openOrders=1')
    expect(cardBlock).not.toContain('/subpkg-order/pages/menu')
  })

  it('labels the payment-success action as 查看本桌订单', () => {
    expect(orderText).toContain("viewDetail: '查看本桌订单'")
    expect(orderText).not.toContain("viewDetail: '查看订单详情'")
  })
})
