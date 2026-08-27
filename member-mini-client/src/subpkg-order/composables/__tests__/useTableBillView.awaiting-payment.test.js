import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ref } from 'vue'
import { useTableBillView } from '../useTableBillView.js'

// 「本桌订单」面板不能把一笔还没收到的钱说成正在正常走流程。
// 起因：一笔 pending_payment 的先付后厨订单挂在面板里过夜，界面同时显示
// 「待支付」+「无需操作，请稍候」+ 一条进度条 + 「已等待 8 小时」——
// 四件东西互相矛盾，而且"无需操作"给的是相反的下一步（顾客恰恰必须去付款）。
//
// 对照知识库：
// - OPPO产品原则：任何异常提示必须自带真实的下一步；颜色即优先级。
// - Jobs产品原则（端到端）：不能让顾客卡在"不知道到底付没付"的状态。

function setup({ status = 'pending_payment', orders = null } = {}) {
  const list = orders ?? [{
    id: '8704',
    orderNo: '8704',
    status,
    diningSessionId: 'sess_1',
    paymentMode: 'prepay',
    items: [{ name: '羊内腰', qty: 1, price: 20 }],
    total: 16,
    createdAt: '02:50',
    createdTs: Date.now() - 8 * 3600 * 1000,
  }]
  return useTableBillView({
    myOrders: ref(list),
    orderId: ref('8704'),
    orderStatus: ref(status),
    paymentMode: ref('prepay'),
    diningSessionId: ref('sess_1'),
    tableSessionTotal: ref(0),
    tableSessionClosed: ref(false),
    tableSessionStatus: ref('OPEN'),
    checkoutRequestedAt: ref(''),
    tableCheckouting: ref(false),
    tableSessionClosedAt: ref(''),
    normalizePaymentMode: (m) => m || 'prepay',
    orderItemQty: (item) => Number(item?.qty || 0),
    orderItemCount: (order) => (order?.items || []).reduce((n, i) => n + Number(i.qty || 0), 0),
  })
}

describe('isAwaitingPayment', () => {
  for (const status of ['pending_payment', 'unpaid', 'need_payment']) {
    it(`把 ${status} 识别为"钱还没收到"`, () => {
      expect(setup({ status }).isAwaitingPayment.value).toBe(true)
    })
  }

  for (const status of ['pending', 'preparing', 'done', 'settled']) {
    it(`不把已付款的 ${status} 误判成未支付`, () => {
      expect(setup({ status }).isAwaitingPayment.value).toBe(false)
    })
  }

  it('没有任何订单时为 false，不抛错', () => {
    expect(setup({ orders: [] }).isAwaitingPayment.value).toBe(false)
  })
})

describe('未支付时的下一步文案', () => {
  it('给出真实的下一步（去付款），不是"无需操作，请稍候"', () => {
    const view = setup({ status: 'pending_payment' })
    expect(view.tableOrderNextAction.value).toContain('支付')
    expect(view.tableOrderNextAction.value).not.toContain('无需操作')
  })

  it('已付款待接单仍然是"无需操作，请稍候"（这时确实不用管）', () => {
    expect(setup({ status: 'pending' }).tableOrderNextAction.value).toBe('无需操作，请稍候')
  })
})

describe('normalizeOrderStatus 承重墙未被改动', () => {
  // isAwaitingPayment 是纯展示派生。normalizeOrderStatus 被 allOrdersDone /
  // isTableSettled / canCheckout 依赖，pending_payment 在那里仍然落到 'pending'，
  // 结算状态机的行为必须保持原样。
  it('pending_payment 在结算口径里仍归一化为 pending', () => {
    expect(setup().normalizeOrderStatus('pending_payment')).toBe('pending')
  })
})

describe('静态合同：面板不再展示孤立的等待时长', () => {
  const read = (rel) => {
    const here = path.dirname(fileURLToPath(import.meta.url))
    return fs.readFileSync(path.resolve(here, rel), 'utf8')
  }

  it('两个弹层和共享卡片样式里都没有"已等待"这类孤立时长数字', () => {
    // OPPO 规则：数字必须带场景。"已等待 8 小时"既不说明还要等多久，
    // 也不给下一步动作。真要做时间感必须是后端出餐预估（ETA）。
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).not.toContain('已等待')
      expect(source).not.toContain('WaitText')
    }
  })

  it('两个弹层都没有进度条——状态只用状态胶囊一种表达', () => {
    // 顾客是来吃饭的，不是来看订单状态机的。四个状态一次性摊开给顾客，
    // 跟顶部胶囊说的是同一件事，属于同一功能的第二种交互。
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).not.toContain('to-track')
      expect(source).not.toContain('Timeline')
    }
  })

  it('未支付有独立配色，不跟"待接单"同色', () => {
    const scss = read('../../components/table-order-card.scss')
    expect(scss).toContain('.to-card--unpaid')
    const source = read('../../components/OrderHistorySheet.vue')
    expect(source).toContain("return 'unpaid'")
  })
})
