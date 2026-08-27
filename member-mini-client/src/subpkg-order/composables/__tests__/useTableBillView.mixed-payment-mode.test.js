import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useTableBillView } from '../useTableBillView.js'

// 现场问题：商家后台一桌显示 4 单，小程序「本桌订单」只显示 3 单。
//
// 起因是店铺在同一个 dining_session 存续期间把收款模式从「先付后厨」切成了
// 「桌台账单」，于是会话里同时存在 prepay 和 table_account 两种订单。
// tableSessionOrders 只认 table_account/postpay，prepay 那一单在顾客端整条消失
// ——顾客看不到自己点的菜，可能重复下单。
//
// 修法：展示口径（会话全量）和结算口径（只含 table_account/postpay）拆成两条。
// 菜要显示，钱不能并进应付金额（prepay 已各自付清，并进去等于收两次钱）。

const SESSION = 'sess_A12'

function order(overrides) {
  return {
    diningSessionId: SESSION,
    items: [],
    total: 0,
    discountAmount: 0,
    createdTs: 1000,
    createdAt: '03:13',
    ...overrides,
  }
}

// 复刻现场那一桌：#7152 是切模式之前的 prepay 单，其余三单是 table_account。
const MIXED_TABLE = [
  order({ id: '7152', orderNo: '7152', status: 'preparing', paymentMode: 'prepay', createdAt: '11:38', createdTs: 1000, total: 0.01, items: [{ name: '测试支付', qty: 1 }] }),
  order({ id: '6608', orderNo: '6608', status: 'preparing', paymentMode: 'table_account', createdAt: '03:13', createdTs: 2000, total: 0.02, items: [{ name: '退款测试', qty: 1 }] }),
  order({ id: '9232', orderNo: '9232', status: 'pending', paymentMode: 'table_account', createdAt: '03:13', createdTs: 3000, total: 0.01, items: [{ name: '测试支付', qty: 1 }] }),
  order({ id: '8176', orderNo: '8176', status: 'pending', paymentMode: 'table_account', createdAt: '03:14', createdTs: 4000, total: 48.80, discountAmount: 1, items: [{ name: '回锅肉', qty: 1 }] }),
]

function setup(orders = MIXED_TABLE, { paymentMode = 'table_account' } = {}) {
  return useTableBillView({
    myOrders: ref(orders),
    orderId: ref(''),
    orderStatus: ref('pending'),
    paymentMode: ref(paymentMode),
    diningSessionId: ref(SESSION),
    tableSessionTotal: ref(0),
    tableSessionClosed: ref(false),
    tableSessionStatus: ref('OPEN'),
    checkoutRequestedAt: ref(''),
    tableCheckouting: ref(false),
    tableSessionClosedAt: ref(''),
    normalizePaymentMode: (m) => (['prepay', 'postpay', 'table_account'].includes(String(m || '')) ? String(m) : 'prepay'),
    orderItemQty: (item) => Number(item?.qty || 0),
    orderItemCount: (o) => (o?.items || []).reduce((n, i) => n + Number(i.qty || 0), 0),
  })
}

describe('展示口径：会话内全部订单都要出现在本桌订单里', () => {
  it('后台 4 单，顾客端也是 4 单（不再吞掉 prepay 那一单）', () => {
    expect(setup().tableOrderGroups.value).toHaveLength(4)
  })

  it('prepay 那一单带 isPrepaid 标记，其余不带', () => {
    const groups = setup().tableOrderGroups.value
    const byNo = Object.fromEntries(groups.map(g => [g.orderNo, g]))
    expect(byNo['7152'].isPrepaid).toBe(true)
    expect(byNo['6608'].isPrepaid).toBe(false)
    expect(byNo['9232'].isPrepaid).toBe(false)
    expect(byNo['8176'].isPrepaid).toBe(false)
  })

  it('按下单时间升序，最早那一单标"下单"，其余标"加菜"', () => {
    const groups = setup().tableOrderGroups.value
    expect(groups.map(g => g.orderNo)).toEqual(['7152', '6608', '9232', '8176'])
    expect(groups[0].title).toContain('下单')
    expect(groups[1].title).toContain('加菜')
  })
})

describe('结算口径：prepay 的钱绝不能并进本桌应付金额', () => {
  it('tableTotal 只算 table_account/postpay，不含已单独付款的 prepay', () => {
    // 0.02 + 0.01 + 48.80 = 48.83，与后台「待结账」一致；不含 prepay 的 0.01。
    expect(setup().tableTotal.value).toBeCloseTo(48.83, 2)
  })

  it('tableItemCount 同样只算待结账的部分', () => {
    expect(setup().tableItemCount.value).toBe(3)
  })

  it('已单独付款的菜靠 isPrepaid 在菜品行标"已付"，合计因此自己解释得通', () => {
    // 菜品行金额合计 0.01(已付) + 0.02 + 0.01 + 49.80 = 49.84，
    // 减掉标了"已付"的 0.01 和优惠 1.00，正好是待结账 48.83。
    const groups = setup().tableOrderGroups.value
    const prepaid = groups.filter(g => g.isPrepaid)
    expect(prepaid).toHaveLength(1)
    expect(prepaid[0].orderNo).toBe('7152')
  })

  it('纯 table_account 会话里没有任何"已付"标记', () => {
    const view = setup(MIXED_TABLE.filter(o => o.paymentMode !== 'prepay'))
    expect(view.tableOrderGroups.value).toHaveLength(3)
    expect(view.tableOrderGroups.value.some(g => g.isPrepaid)).toBe(false)
  })
})

describe('结账闸门口径必须跟后端 settle_table 对齐', () => {
  // settle_table 按 dining_session_id 捞全部订单，blocking_orders 里任何一单不在
  // TABLE_CLOSE_DONE_STATUSES 就整桌 409「本桌还有未完成的订单，无法结账」。
  // 客户端只看 table_account 会放行一个后端必然拒绝的结账请求。
  const doneTableAccount = [
    order({ id: 'a', orderNo: 'a', status: 'done', paymentMode: 'table_account', total: 10, items: [{ name: '菜A', qty: 1 }] }),
  ]

  it('同会话还有制作中的 prepay 单时，不放行"去结账"', () => {
    const view = setup([
      ...doneTableAccount,
      order({ id: 'b', orderNo: 'b', status: 'preparing', paymentMode: 'prepay', createdTs: 5000, total: 5, items: [{ name: '菜B', qty: 1 }] }),
    ])
    expect(view.allOrdersDone.value).toBe(false)
    expect(view.canCheckout.value).toBe(false)
    expect(view.stillPreparing.value).toBe(true)
  })

  it('会话内全部订单都 done 时正常放行', () => {
    const view = setup([
      ...doneTableAccount,
      order({ id: 'b', orderNo: 'b', status: 'done', paymentMode: 'prepay', createdTs: 5000, total: 5, items: [{ name: '菜B', qty: 1 }] }),
    ])
    expect(view.allOrdersDone.value).toBe(true)
    expect(view.canCheckout.value).toBe(true)
  })

  it('已取消的 prepay 单不算未完成，不应该永久挡住结账', () => {
    const view = setup([
      ...doneTableAccount,
      order({ id: 'b', orderNo: 'b', status: 'cancelled', paymentMode: 'prepay', createdTs: 5000, total: 5, items: [{ name: '菜B', qty: 1 }] }),
    ])
    expect(view.allOrdersDone.value).toBe(true)
    expect(view.canCheckout.value).toBe(true)
  })
})

describe('整桌状态按展示口径', () => {
  it('同会话 prepay 单还在制作中时，顶部不能说"菜品已上齐"', () => {
    const view = setup([
      order({ id: 'a', orderNo: 'a', status: 'done', paymentMode: 'table_account', total: 10, items: [{ name: '菜A', qty: 1 }] }),
      order({ id: 'b', orderNo: 'b', status: 'preparing', paymentMode: 'prepay', createdTs: 5000, total: 5, items: [{ name: '菜B', qty: 1 }] }),
    ])
    expect(view.tableStatusView.value.title).toBe('菜品正在制作')
  })

  it('还有单没被接下时，顶部说的是"商家正在确认订单"', () => {
    expect(setup().tableStatusView.value.title).toBe('订单已收到')
  })
})

describe('默认视图的份数是"点了多少菜"，不是"这次结账里有多少菜"', () => {
  it('displayItemCount 数全桌 4 份，tableItemCount 仍只数待结账的 3 份', () => {
    const view = setup()
    expect(view.displayItemCount.value).toBe(4)
    expect(view.tableItemCount.value).toBe(3)
  })

  it('优惠汇总到一处，不再只藏在某一单的批次头里', () => {
    expect(setup().tableDiscountTotal.value).toBeCloseTo(1, 2)
  })
})

describe('每道菜的进度档位', () => {
  // 后端只有 pending / preparing / done 三个真实档位。第 4 档 settled(已结账)
  // 是整桌事件不是这道菜的事件——曾经把它当第 4 档，导致菜早就上齐了、
  // 进度却永远差一格，非要等整桌结账才填满。
  const stageOf = (status) => {
    const view = setup([order({ id: 's', orderNo: 's', status, paymentMode: 'table_account', total: 1, items: [{ name: '菜', qty: 1 }] })])
    return view.tableOrderGroups.value[0].stage
  }

  it('档数是 3，跟后端真实档位一致', () => {
    expect(setup().ORDER_STAGE_COUNT).toBe(3)
  })

  it('待接单走 1 步，制作中走 2 步', () => {
    expect(stageOf('pending')).toBe(1)
    expect(stageOf('preparing')).toBe(2)
  })

  it('已上餐就是这道菜的终点，进度必须走满（不用等整桌结账）', () => {
    expect(stageOf('done')).toBe(3)
    expect(stageOf('done')).toBe(setup().ORDER_STAGE_COUNT)
  })

  it('已结账同样是终点', () => {
    expect(stageOf('settled')).toBe(3)
  })

  it('已取消 / 已拒单给 -1：那是"这道菜没了"，不是"进度停在某一步"', () => {
    expect(stageOf('cancelled')).toBe(-1)
    expect(stageOf('rejected')).toBe(-1)
  })
})

describe('桌牌号取会话内任意一单', () => {
  it('只有 prepay 那一单带 pickup_no 时也能取到', () => {
    const view = setup([
      order({ id: 'a', orderNo: 'a', status: 'pending', paymentMode: 'table_account', total: 10, items: [] }),
      order({ id: 'b', orderNo: 'b', status: 'pending', paymentMode: 'prepay', createdTs: 5000, total: 5, items: [], pickupNo: '14' }),
    ])
    expect(view.tablePickupNo.value).toBe('14')
  })
})

describe('别的桌的订单仍然不会串进来', () => {
  it('不同 dining_session 的订单一律排除', () => {
    const view = setup([
      ...MIXED_TABLE,
      order({ id: 'x', orderNo: 'x', status: 'pending', paymentMode: 'prepay', diningSessionId: 'sess_OTHER', total: 99, items: [{ name: '别桌的菜', qty: 1 }] }),
    ])
    expect(view.tableOrderGroups.value).toHaveLength(4)
    expect(view.tableOrderGroups.value.map(g => g.orderNo)).not.toContain('x')
  })
})
