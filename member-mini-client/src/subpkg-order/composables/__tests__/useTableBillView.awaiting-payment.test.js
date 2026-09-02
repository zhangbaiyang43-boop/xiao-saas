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

describe('group.isAwaitingPayment —— 每个分单的「未跨过支付边界」信号', () => {
  // 「本桌进度」呼吸灯的 frontier 必须排除未支付单。这个 per-group 信号来自
  // 后端 raw status，绝不能因为 normalizeOrderStatus('pending_payment') → 'pending'
  // → orderStageIndex → stage 1 而在归一化里丢掉。
  for (const status of ['pending_payment', 'unpaid', 'need_payment']) {
    it(`raw status ${status} → group.isAwaitingPayment = true`, () => {
      const groups = setup({ status }).tableOrderGroups.value
      expect(groups[0].isAwaitingPayment).toBe(true)
    })
  }

  for (const status of ['pending', 'preparing', 'done', 'settled']) {
    it(`raw status ${status} → group.isAwaitingPayment = false`, () => {
      const groups = setup({ status }).tableOrderGroups.value
      expect(groups[0].isAwaitingPayment).toBe(false)
    })
  }

  it('pending_payment 的分单：stage 仍是 1，但 isAwaitingPayment 是 true（信号没被 normalize 吃掉）', () => {
    const groups = setup({ status: 'pending_payment' }).tableOrderGroups.value
    expect(groups[0].stage).toBe(1)
    expect(groups[0].isAwaitingPayment).toBe(true)
  })

  it('未支付单仍留在 tableOrderGroups 里（只是不驱动呼吸，不从列表里删）', () => {
    const mixed = [
      { id: 'a', orderNo: 'a', status: 'pending_payment', diningSessionId: 'sess_1', paymentMode: 'prepay', items: [{ name: '未付的菜', qty: 1, price: 10 }], total: 10, createdAt: '10:00', createdTs: 1000 },
      { id: 'b', orderNo: 'b', status: 'preparing', diningSessionId: 'sess_1', paymentMode: 'table_account', items: [{ name: '在做的菜', qty: 1, price: 20 }], total: 20, createdAt: '10:05', createdTs: 2000 },
    ]
    const groups = setup({ orders: mixed }).tableOrderGroups.value
    expect(groups).toHaveLength(mixed.length)
    expect(groups.some(g => g.isAwaitingPayment === true)).toBe(true)
    expect(groups.some(g => g.isAwaitingPayment === false)).toBe(true)
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

  it('废弃的四步整卡进度条（tableBillTimeline / tableOrderTimeline）没有回归', () => {
    // 早期两个弹层各带一条「已下单 → 接单 → 上齐 → 结账」四步 timeline
    // （含 .to-track 元素和 *Timeline 计算），已按产品决定删除
    // （见 useTableBillView.js 里两处「已删除」注释）。
    // 用户后来要求的三阶段「呼吸」轻量状态指示是另一回事，由
    // table-order-progress.contract.test.js 负责——这里只守「旧四步 timeline 不回来」。
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).not.toContain('to-track')
      expect(source).not.toContain('Timeline')
    }
  })

  it('进度靠菜品行左侧的点表达，不配解释文字', () => {
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).toContain('to-stage-dot')
      expect(source).toContain("row.stage >= n")
    }
  })

  it('正常流程不出状态解释句，只有"需要顾客动手"时才出文字', () => {
    // 先付后厨那张卡的状态胶囊 + 下一步文案，只在未支付时渲染。
    const source = read('../../components/OrderHistorySheet.vue')
    expect(source).toContain('v-if="isAwaitingPayment" class="to-head-status"')
  })

  it('进度点旁边不再有文字图例——顾客用几次就知道点代表什么', () => {
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).not.toContain('to-legend')
      expect(source).not.toContain('stageLabels')
    }
  })

  it('桌号和桌牌号同一行居中展示（一块桌牌），不再是右上角两行附注', () => {
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).toContain('class="to-plate"')
      expect(source).not.toContain('to-ident')
    }
  })

  it('两个弹层的头部一致：左标题 + 右上角圆形关闭，没有额外的返回箭头', () => {
    // base-sheet 只要不传 header-left 就是这套默认头部；传了会切到
    // --leading 分支把标题居中、关闭键挤到标题旁边，两个弹层就长得不一样了。
    for (const rel of ['../../components/TableBillSheet.vue', '../../components/OrderHistorySheet.vue']) {
      const source = read(rel)
      expect(source).not.toContain('#header-left')
      expect(source).not.toContain('icon-back')
    }
  })

  it('未支付有独立配色，不跟"待接单"同色', () => {
    const scss = read('../../components/table-order-card.scss')
    expect(scss).toContain('.to-card--unpaid')
    const source = read('../../components/OrderHistorySheet.vue')
    expect(source).toContain("return 'unpaid'")
  })
})
