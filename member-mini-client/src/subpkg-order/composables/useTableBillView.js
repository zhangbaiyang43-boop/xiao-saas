import { computed } from 'vue'
import { formatOrderStatusText } from '@/utils/orderStatus'

// 从 menu.vue 拆出来的"桌台账单/单笔订单进度"展示逻辑——本桌当前订单是哪一单、
// 桌台账单（拼单/餐后付款）要不要显示结账按钮、订单进度条的文案图标——全都是
// 只读派生计算（不涉及网络/存储）。逻辑跟原来在 menu.vue 里的一字未改，只是搬了个
// 位置。
//
// 特意没有拆进来的东西，留在 menu.vue 里：
// - normalizePaymentMode：定义在 menu.vue 更靠前的位置，syncDiningOrders 等
//   拉取/写入订单数据的高风险流程也在用它，不是这个视图层专属的。
// - markOrderItemImageFailed：只是个小 setter，跟这里的展示计算没有实质关联。
// - 所有会写 myOrders/tableSessionStatus/tableSessionClosed 等状态的函数
//   （syncDiningOrders、performTableCheckout 等）——它们是数据的唯一写入方，
//   这个组合式函数只读不写，避免读写分散在两个文件里增加追查状态变化的难度。
export function useTableBillView({
  myOrders, orderId, orderStatus, paymentMode, diningSessionId,
  tableSessionTotal, tableSessionClosed, tableSessionStatus, checkoutRequestedAt,
  tableCheckouting, tableSessionClosedAt,
  normalizePaymentMode, orderItemQty, orderItemCount,
}) {
  const normalizeOrderStatus = (status) => {
    if (['paid', 'pending'].includes(status)) return 'pending'
    if (['accepted', 'preparing', 'cooking'].includes(status)) return 'preparing'
    if (['done', 'completed'].includes(status)) return 'done'
    if (status === 'settled') return 'settled'
    if (['cancelled', 'rejected'].includes(status)) return status
    return 'pending'
  }

  const activeOrderRank = (order) => {
    const status = normalizeOrderStatus(order?.status)
    if (['pending', 'preparing'].includes(status)) return 0
    if (status === 'done') return 1
    return 2
  }

  const currentTableOrder = computed(() => {
    if (!myOrders.value.length) return null
    const active = [...myOrders.value]
      .filter(order => !['cancelled', 'rejected'].includes(normalizeOrderStatus(order.status)))
      .sort((a, b) => activeOrderRank(a) - activeOrderRank(b))[0]
    if (active) return active
    // 全部订单都已取消/拒单时，只有当前设备正在跟踪的那单才继续展示"异常状态"，
    // 避免把本桌历史上别人取消的旧单当成当前顾客的订单弹出来。
    return myOrders.value.find(order => order.id === orderId.value) || null
  })

  const historyTableOrders = computed(() =>
    myOrders.value.filter(order => !currentTableOrder.value || order.id !== currentTableOrder.value.id)
  )

  // P1 修复：menu.vue 之前把 `tablePickupNo` 当 useTableBillView 的返回值解构，
  // 但这个组合式函数从来没有产出过这个字段——传给 TableBillSheet 的桌牌号
  // 从源头就是 undefined，不只是子组件没声明 prop 的问题。桌牌号是按桌台会话
  // 发一次（哪个批次拿到号不重要），取第一笔带了 pickup_no 的订单即可，
  // 跟 admin-h5 OrderManage.vue 里 `orders.find(o => o.pickup_no)` 同一套算法。
  // 展示口径：桌牌号是按会话发一次，会话里任何一单带的号都是同一个——包括 prepay 单。
  const tablePickupNo = computed(() => sessionDisplayOrders.value.find(order => order.pickupNo)?.pickupNo || '')
  const isTableAccountMode = computed(() => paymentMode.value === "table_account")
  const isPostpayMode = computed(() => paymentMode.value === "postpay")
  // 餐后付款和桌台账单，后端其实是同一套机制：同一桌多次下单共用同一个 dining_session，
  // 商家在后台也是按整桌一次性结账（settle-table），不是按单笔结账。小程序这边如果还是把
  // 餐后付款当成"每笔订单各自一个独立进度条"来展示，就跟后端的真实行为对不上——这里统一
  // 用"共享账单模式"复用桌台账单那套汇总视图，只是底部动作不同（见下面 canCheckout 附近）。
  const isSharedBillMode = computed(() => isTableAccountMode.value || isPostpayMode.value)
  const sharedBillSubLabel = computed(() => isPostpayMode.value ? '堂食 · 餐后统一结账' : '堂食 · 本桌统一结账')
  const tableSessionId = computed(() => String(diningSessionId.value || uni.getStorageSync('dining_session_id') || ''))
  const isSameDiningSessionOrder = (order) => {
    const orderSessionId = String(order?.diningSessionId || order?.tableSessionId || '')
    if (!tableSessionId.value || !orderSessionId) return false
    return orderSessionId === tableSessionId.value
  }
  const byCreatedTs = (a, b) => Number(a.createdTs || 0) - Number(b.createdTs || 0)
  const isPrepaidOrder = (order) =>
    normalizePaymentMode(order?.paymentMode || paymentMode.value) === 'prepay'

  // 展示口径 vs 结算口径，是两件不同的事，必须分开算：
  //
  // - sessionDisplayOrders（展示）：本桌会话里的**全部**订单。老板在后台看到的就是
  //   这一份（settle_table 也是按 dining_session_id 捞全部订单，不分支付方式）。
  // - tableSessionOrders（结算）：只含 table_account / postpay。先付后厨（prepay）的
  //   单在下单时已经各自付清，绝不能并进"本桌待结账金额"，否则顾客要为同一道菜付两次钱。
  //
  // 原来只有后者一条口径，导致店铺中途切换收款模式后，会话里的 prepay 订单在顾客端
  // "本桌订单"里**整条消失**——后台 4 单、小程序 3 单，顾客看不到自己点的菜。
  const sessionDisplayOrders = computed(() =>
    myOrders.value.filter(isSameDiningSessionOrder).sort(byCreatedTs)
  )
  const tableSessionOrders = computed(() =>
    myOrders.value
      .filter(order => ['table_account', 'postpay'].includes(normalizePaymentMode(order?.paymentMode || paymentMode.value)))
      .filter(isSameDiningSessionOrder)
      .sort(byCreatedTs)
  )
  const isOrderInvalid = (order) => ['cancelled', 'rejected'].includes(normalizeOrderStatus(order?.status))
  const isItemInvalid = (item) => ['refunded', 'refund', 'cancelled', 'canceled'].includes(String(item?.status || item?.refund_status || '').toLowerCase())
  const validTableOrders = computed(() => tableSessionOrders.value.filter(order => !isOrderInvalid(order)))
  const validDisplayOrders = computed(() => sessionDisplayOrders.value.filter(order => !isOrderInvalid(order)))
  const tableTotal = computed(() => {
    if (Number(tableSessionTotal.value) > 0) return Number(tableSessionTotal.value)
    const backendTotal = validTableOrders.value.map(order => Number(order.tableTotal || 0)).find(total => total > 0)
    if (backendTotal) return backendTotal
    return validTableOrders.value.reduce((sum, order) => sum + Number(order.total || 0), 0)
  })
  const countItems = (orders) =>
    orders.reduce((sum, order) => sum + (order.items || []).reduce((itemSum, item) => itemSum + (isItemInvalid(item) ? 0 : orderItemQty(item)), 0), 0)
  // 结算口径的份数：gate canCheckout 用，跟 tableTotal 同一批订单。
  const tableItemCount = computed(() => countItems(validTableOrders.value))
  // 展示口径的份数：顾客问的是"我点了多少菜"，答案是这一桌全部的菜，
  // 不是"这次要结的账里有多少菜"。
  const displayItemCount = computed(() => countItems(validDisplayOrders.value))
  // PRODUCT_RULES 第4条：优惠必须一眼可见。原来它藏在每一单的批次头里，
  // 顾客要展开分单才看得到自己省了多少。
  const tableDiscountTotal = computed(() =>
    validTableOrders.value.reduce((sum, order) => sum + Number(order.discountAmount || 0), 0)
  )
  const tableGroupStatusText = (status, statusText) => formatOrderStatusText(status, statusText)
  const tableGroupStatusTone = (status) => {
    const normalized = normalizeOrderStatus(status)
    if (['cancelled', 'rejected'].includes(normalized)) return 'muted'
    if (normalized === 'settled') return 'settled'
    if (normalized === 'done') return 'served'
    return 'active'
  }
  // 拼桌时同一桌可能好几个人各自的手机都在下单，用固定的一组颜色循环分配，
  // 不够用就从头再来一轮——纯展示用的编号，跟真实身份无关，参考大厂拼单点餐的做法。
  const PARTICIPANT_COLORS = ['#07C160', '#FF7D45', '#5B8FF9', '#F5A623', '#B37FEB', '#3ABBB0']
  const participantColor = (no) => {
    if (!no || no < 1) return PARTICIPANT_COLORS[0]
    return PARTICIPANT_COLORS[(no - 1) % PARTICIPANT_COLORS.length]
  }
  // 分单数据。默认视图不展示它——顾客问的是"点了多少菜、花了多少钱"，
  // 「第几单、几点几分、单号多少」是系统怎么组织这些菜的，收在「订单详情」里，
  // 想看再展开（PRODUCT_RULES 第3条：细节默认折叠）。
  const buildOrderGroups = (orders) =>
    orders.map((order, index) => ({
      id: order.id || String(index),
      orderNo: order.orderNo || String(order.id || '').slice(-4),
      title: (order.createdAt || '--:--') + (index === 0 ? ' 下单' : ' 加菜'),
      statusText: tableGroupStatusText(order.status, order.status_text),
      tone: tableGroupStatusTone(order.status),
      isPrepaid: isPrepaidOrder(order),
      discountAmount: Number(order.discountAmount || 0),
      participantNo: order.participantNo || null,
      participantColor: participantColor(order.participantNo),
      isStaff: Boolean(order.isStaff),
      staffNote: order.staffNote || '',
      items: (order.items || []).map(item => ({
        ...item,
        isInvalid: isOrderInvalid(order) || isItemInvalid(item),
        invalidText: isOrderInvalid(order) ? '已取消' : '已退菜',
      })),
    }))

  // 展示口径：会话内全部订单。prepay 的批次带 isPrepaid，菜品行标"已付"，
  // 让顾客知道这道菜在本桌、但不在这次要结的账里。
  const tableOrderGroups = computed(() =>
    buildOrderGroups(sessionDisplayOrders.value)
  )
  // 先付后厨侧的同款分单数据（当前这一笔 + 历史订单），让两个弹层的
  // 「订单详情」折叠区用同一套渲染，不再各写一份。
  const orderHistoryGroups = computed(() =>
    buildOrderGroups([...orderHistoryOrders.value].sort(byCreatedTs))
  )
  const isTableSettled = computed(() => {
    if (tableSessionClosed.value) return true
    if (tableSessionStatus.value === 'CLOSED') return true
    return tableSessionOrders.value.length > 0 && tableSessionOrders.value.every(order => normalizeOrderStatus(order.status) === 'settled')
  })
  const canContinueOrder = computed(() => isSharedBillMode.value && !tableSessionClosed.value && tableSessionStatus.value !== 'CLOSED')
  // 桌台账单/餐后付款都必须等本桌所有有效订单都做完（done）才算"可以结账"，否则会出现
  // 桌台账单顾客点了"去结账"、商家在后台点结账时却被后端 settle-table 以"本桌还有未完成
  // 的订单"拒绝的落差；餐后付款虽然没有"去结账"按钮，但同样的判断决定要不要提示去收银台。
  //
  // 口径必须跟后端一致：settle_table 按 dining_session_id 捞**全部**订单，
  // blocking_orders 里任何一单不在 TABLE_CLOSE_DONE_STATUSES 就整桌 409。所以这里也要
  // 按会话全量判断——只看 table_account/postpay 会漏掉同会话里还在制作中的 prepay 单，
  // 那正是上面这段注释想避免的那个落差。
  const allOrdersDone = computed(() =>
    validDisplayOrders.value.length > 0 && validDisplayOrders.value.every(order => normalizeOrderStatus(order.status) === 'done')
  )
  const stillPreparing = computed(() => tableOrderGroups.value.length > 0 && !isTableSettled.value && !allOrdersDone.value)
  const checkoutRequested = computed(() => Boolean(checkoutRequestedAt.value))
  // 只有桌台账单才有"去结账"这个可点击的自助操作——餐后付款结账动作在商家手里
  // （收银台/服务员操作后台"结账"按钮），小程序这边只负责提示，不提供可点的按钮。
  const canCheckout = computed(() =>
    isTableAccountMode.value && tableItemCount.value > 0 && !isTableSettled.value && !tableCheckouting.value && allOrdersDone.value
  )
  const postpayReadyToSettle = computed(() =>
    isPostpayMode.value && tableItemCount.value > 0 && !isTableSettled.value && allOrdersDone.value
  )
  const formatClosedAtTime = (raw) => {
    if (!raw) return ''
    const d = new Date(raw)
    if (Number.isNaN(d.getTime())) return ''
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
  }
  const tableStatusView = computed(() => {
    if (isTableSettled.value) {
      const closedTimeText = formatClosedAtTime(tableSessionClosedAt.value)
      const payNote = isTableAccountMode.value
        ? '由商家柜台现结，无需再次付款'
        : (isPostpayMode.value ? '已在收银台完成支付' : '')
      return {
        icon: 'icon-roundcheckfill',
        title: '本桌已结账',
        desc: closedTimeText ? `本次用餐已完成 · 结账时间 ${closedTimeText}` : '本次用餐已完成',
        note: payNote,
        tone: 'settled',
      }
    }
    if (!tableOrderGroups.value.length) return { icon: 'icon-list', title: '本桌还没有已点菜品', desc: '先点菜，后续加菜会自动合并', tone: 'settled' }
    // 展示口径：顶部这句话描述的是"这一桌的菜现在什么情况"，必须涵盖会话里全部订单，
    // 否则同会话的 prepay 单还在制作中，顶部却会说"菜品已上齐"。
    const statuses = validDisplayOrders.value.map(order => normalizeOrderStatus(order.status))
    if (statuses.includes('pending')) return { icon: 'icon-timefill', title: '订单已收到', desc: '商家正在确认订单，请稍候', tone: 'active' }
    if (statuses.includes('preparing')) return { icon: 'icon-beican', title: '菜品正在制作', desc: '厨房正在制作，可以继续加菜', tone: 'active' }
    if (statuses.includes('done')) {
      if (isPostpayMode.value) {
        return { icon: 'icon-roundcheckfill', title: '菜品已上齐', desc: '用餐结束请到收银台或联系服务员结账', tone: 'served' }
      }
      return checkoutRequested.value
        ? { icon: 'icon-roundcheckfill', title: '已呼叫服务员', desc: '请稍候，服务员马上为您结账', tone: 'served' }
        : { icon: 'icon-roundcheckfill', title: '菜品已上齐', desc: '吃好后可统一结账', tone: 'served' }
    }
    return { icon: 'icon-beican', title: '商家已接单', desc: '厨房正在为您制作，可以继续加菜', tone: 'active' }
  })

  // 这里曾经有一条四步进度条（tableBillStageIndex / tableBillTimeline），已删除。
  // 顾客是来吃饭的，不是来看订单状态机的：同一件事只用一种表达，
  // 「现在是什么状态」由 tableStatusView 的状态胶囊 + 一句提示单独负责，
  // 不需要再把「已下单/接单/上齐/结账」四个状态一次性摊给顾客看。
  // 每一单各自的状态仍然有，收在「订单详情」折叠区里（tableOrderGroups.statusText）。
  const tableBillPayStateText = computed(() => {
    if (isTableSettled.value) return '已结账'
    return isPostpayMode.value ? '餐后统一结账' : '待结账'
  })

  const currentTableOrderStatus = computed(() => normalizeOrderStatus(currentTableOrder.value?.status || orderStatus.value))

  // 「这一单的钱到底收没收到」——纯展示派生，读后端 raw status，不进
  // normalizeOrderStatus。normalizeOrderStatus 是结算状态机的承重墙
  // （allOrdersDone / isTableSettled / canCheckout 都依赖它，pending_payment
  // 在那里落到 'pending'），动它会波及桌台结算判断；这里只解决"界面上不能把
  // 一笔没收到的钱说成已经在正常走流程"。
  const AWAITING_PAYMENT_STATUSES = ['pending_payment', 'unpaid', 'need_payment']
  const isAwaitingPayment = computed(() =>
    AWAITING_PAYMENT_STATUSES.includes(String(currentTableOrder.value?.status || ''))
  )

  const tableOrderStatusTone = computed(() => {
    if (!currentTableOrder.value) return 'empty'
    const status = currentTableOrderStatus.value
    if (['cancelled', 'rejected'].includes(status)) return 'canceled'
    if (status === 'pending') return 'paid'
    if (status === 'preparing') return 'preparing'
    if (status === 'done') return 'served'
    if (status === 'settled') return 'settled'
    return 'paid'
  })

  const tableOrderStatusBadge = computed(() => formatOrderStatusText(
    currentTableOrder.value?.status || orderStatus.value,
    currentTableOrder.value?.status_text,
  ))

  const tableOrderStatusIcon = computed(() => ({
    canceled: 'icon-warnfill',
    paid: 'icon-pay',
    preparing: 'icon-beican',
    served: 'icon-deliver',
    settled: 'icon-roundcheckfill',
  })[tableOrderStatusTone.value] || 'icon-pay')

  const tableOrderNextAction = computed(() => {
    // 未支付时说"无需操作，请稍候"是给了相反的下一步——这一单恰恰卡在需要顾客
    // 去付款。OPPO 规则：任何异常提示必须自带真实的下一步。
    if (isAwaitingPayment.value) return '这一单还没付款，请完成微信支付'
    return ({
      canceled: '重新点餐',
      paid: '无需操作，请稍候',
      preparing: '等待上餐即可',
      served: '请确认菜品',
      settled: '可关闭查看',
    })[tableOrderStatusTone.value] || '无需操作，请稍候'
  })

  const tableOrderPrimaryButtonText = computed(() => ({
    empty: '去点餐',
    canceled: '重新点餐',
    paid: '我知道了',
    preparing: '我知道了',
    served: '确认已收到',
    settled: '关闭',
  })[tableOrderStatusTone.value] || '我知道了')

  const tableOrderStatusTitle = computed(() => ({
    pending: '商家正在确认订单',
    preparing: '商家已接单，正在制作',
    done: '餐品已上餐，请留意',
    settled: '本桌订单已完成',
    rejected: '订单异常，请联系商家',
    cancelled: '订单已取消',
  })[currentTableOrderStatus.value] || '商家正在确认订单')

  const tableOrderStatusHint = computed(() => {
    if (!currentTableOrder.value) return '暂无本桌订单'
    return ['done', 'settled'].includes(currentTableOrderStatus.value) ? '请留意取餐或服务员通知' : '无需操作，请安心等待'
  })

  // 这里曾经有 tableOrderTimeline（先付后厨的四步进度条），已删除，理由同
  // tableBillTimeline：状态只用状态胶囊一种表达，不把四个状态一次性摊给顾客。

  const currentOrderItemCount = computed(() => orderItemCount(currentTableOrder.value))
  const currentOrderItems = computed(() => currentTableOrder.value?.items || [])

  const currentOrderMainItemText = computed(() => {
    const items = currentTableOrder.value?.items || []
    if (!items.length) return '暂无商品'
    const first = items[0]
    const suffix = items.length > 1 ? ' 等' + items.length + '种' : ''
    return first.name + ' x' + first.qty + suffix
  })
  const pendingOrderCount = computed(() =>
    myOrders.value.filter(o => !['settled', 'cancelled', 'rejected'].includes(normalizeOrderStatus(o.status))).length
  )

  // P1：非分账模式（prepay）下 OrderHistorySheet 只展示"当前这一笔"的金额/份数，
  // 多次加菜后顾客要自己心算历史订单加总——tableTotal/tableItemCount 是分账模式
  // 专属的（后端 table_total 本身就按 payment_mode in (table_account, postpay)
  // 过滤，prepay 订单永远不计入），不能直接复用。这里是纯前端对"这一桌已经点过
  // 的、还在展示范围内的订单"（currentTableOrder + historyTableOrders，
  // 跟 OrderHistorySheet 实际渲染的历史列表同一份数据）做加总，只是一个展示性的
  // "已点了多少"小结，不是"应付金额"——prepay 每笔订单已经各自付清，不存在欠款。
  const orderHistoryOrders = computed(() => (
    currentTableOrder.value ? [currentTableOrder.value, ...historyTableOrders.value] : historyTableOrders.value
  ))
  const orderHistoryTotal = computed(() =>
    orderHistoryOrders.value.reduce((sum, order) => sum + Number(order.total || 0), 0)
  )
  const orderHistoryItemCount = computed(() =>
    orderHistoryOrders.value.reduce((sum, order) => sum + orderItemCount(order), 0)
  )

  return {
    normalizeOrderStatus,
    currentTableOrder,
    historyTableOrders,
    isTableAccountMode,
    isPostpayMode,
    isSharedBillMode,
    sharedBillSubLabel,
    tableSessionId,
    tableSessionOrders,
    sessionDisplayOrders,
    validTableOrders,
    validDisplayOrders,
    tableTotal,
    tableItemCount,
    displayItemCount,
    tableDiscountTotal,
    tablePickupNo,
    tableOrderGroups,
    orderHistoryGroups,
    isTableSettled,
    canContinueOrder,
    allOrdersDone,
    stillPreparing,
    checkoutRequested,
    canCheckout,
    postpayReadyToSettle,
    tableStatusView,
    tableBillPayStateText,
    currentTableOrderStatus,
    isAwaitingPayment,
    tableOrderStatusTone,
    tableOrderStatusBadge,
    tableOrderStatusIcon,
    tableOrderNextAction,
    tableOrderPrimaryButtonText,
    tableOrderStatusTitle,
    tableOrderStatusHint,
    currentOrderItemCount,
    currentOrderItems,
    currentOrderMainItemText,
    pendingOrderCount,
    orderHistoryTotal,
    orderHistoryItemCount,
  }
}
