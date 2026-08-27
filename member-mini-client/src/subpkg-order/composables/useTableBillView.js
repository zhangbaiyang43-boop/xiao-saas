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
  const tablePickupNo = computed(() => tableSessionOrders.value.find(order => order.pickupNo)?.pickupNo || '')
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
  const tableSessionOrders = computed(() =>
    myOrders.value
      .filter(order => ['table_account', 'postpay'].includes(normalizePaymentMode(order?.paymentMode || paymentMode.value)))
      .filter(isSameDiningSessionOrder)
      .sort((a, b) => Number(a.createdTs || 0) - Number(b.createdTs || 0))
  )
  const isOrderInvalid = (order) => ['cancelled', 'rejected'].includes(normalizeOrderStatus(order?.status))
  const isItemInvalid = (item) => ['refunded', 'refund', 'cancelled', 'canceled'].includes(String(item?.status || item?.refund_status || '').toLowerCase())
  const validTableOrders = computed(() => tableSessionOrders.value.filter(order => !isOrderInvalid(order)))
  const tableTotal = computed(() => {
    if (Number(tableSessionTotal.value) > 0) return Number(tableSessionTotal.value)
    const backendTotal = validTableOrders.value.map(order => Number(order.tableTotal || 0)).find(total => total > 0)
    if (backendTotal) return backendTotal
    return validTableOrders.value.reduce((sum, order) => sum + Number(order.total || 0), 0)
  })
  const tableItemCount = computed(() =>
    validTableOrders.value.reduce((sum, order) => sum + (order.items || []).reduce((itemSum, item) => itemSum + (isItemInvalid(item) ? 0 : orderItemQty(item)), 0), 0)
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
  const tableOrderGroups = computed(() =>
    tableSessionOrders.value.map((order, index) => ({
      id: order.id || String(index),
      orderNo: order.orderNo || String(order.id || '').slice(-4),
      title: (order.createdAt || '--:--') + (index === 0 ? ' 下单' : ' 加菜'),
      statusText: tableGroupStatusText(order.status, order.status_text),
      tone: tableGroupStatusTone(order.status),
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
  const allOrdersDone = computed(() =>
    validTableOrders.value.length > 0 && validTableOrders.value.every(order => normalizeOrderStatus(order.status) === 'done')
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
    const statuses = validTableOrders.value.map(order => normalizeOrderStatus(order.status))
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

  // 方案B：餐后付款 / 桌台账单也要有一条压缩进度条（原来只有 prepay 的
  // tableOrderTimeline）。这里按"整桌"聚合状态推一个 0..4 的阶段下标：
  // 0 还没下单 · 1 已下单待接单 · 2 商家已接单/制作中 · 3 全部上齐待结账 · 4 已结账。
  const tableBillStageIndex = computed(() => {
    if (isTableSettled.value) return 4
    const statuses = validTableOrders.value.map(order => normalizeOrderStatus(order.status))
    if (!statuses.length) return 0
    if (allOrdersDone.value) return 3
    if (statuses.includes('preparing')) return 2
    if (statuses.every(status => status === 'pending')) return 1
    return 2
  })
  const tableBillTimeline = computed(() => {
    const currentIndex = tableBillStageIndex.value
    return [
      { key: 'ordered', label: '已下单' },
      { key: 'accepted', label: '商家接单' },
      { key: 'served', label: '已上齐' },
      { key: 'settled', label: '已结账' },
    ].map((step, index) => ({ ...step, done: index < currentIndex, active: index === currentIndex }))
  })
  const tableBillPayStateText = computed(() => {
    if (isTableSettled.value) return '已结账'
    return isPostpayMode.value ? '餐后统一结账' : '待结账'
  })

  const currentTableOrderStatus = computed(() => normalizeOrderStatus(currentTableOrder.value?.status || orderStatus.value))

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

  const tableOrderNextAction = computed(() => ({
    canceled: '重新点餐',
    paid: '无需操作，请稍候',
    preparing: '等待上餐即可',
    served: '请确认菜品',
    settled: '可关闭查看',
  })[tableOrderStatusTone.value] || '无需操作，请稍候')

  const tableOrderProgressSub = computed(() => ({
    canceled: '无需等待',
    paid: '预计很快接单',
    preparing: '商家处理中',
    served: '可安心用餐',
    settled: '订单完成',
  })[tableOrderStatusTone.value] || '订单进行中')

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

  const tableOrderTimeline = computed(() => {
    const order = ['pending', 'preparing', 'done', 'settled']
    const currentIndex = Math.max(0, order.indexOf(currentTableOrderStatus.value))
    return [
      { key: 'paid', status: 'pending', label: '已支付', icon: 'icon-pay', desc: currentTableOrder.value?.createdAt || '' },
      { key: 'preparing', status: 'preparing', label: '商家已接单', icon: 'icon-beican', desc: currentIndex >= 1 ? '厨房开始处理' : '' },
      { key: 'done', status: 'done', label: '已上餐', icon: 'icon-deliver', desc: currentIndex >= 2 ? '餐品已完成' : '' },
      { key: 'settled', status: 'settled', label: '已完成', icon: 'icon-roundcheckfill', desc: currentIndex >= 3 ? '本桌已结束' : '' },
    ].map((step, index) => ({ ...step, done: index < currentIndex, active: index === currentIndex }))
  })

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
    validTableOrders,
    tableTotal,
    tableItemCount,
    tablePickupNo,
    tableOrderGroups,
    isTableSettled,
    canContinueOrder,
    allOrdersDone,
    stillPreparing,
    checkoutRequested,
    canCheckout,
    postpayReadyToSettle,
    tableStatusView,
    tableBillTimeline,
    tableBillPayStateText,
    currentTableOrderStatus,
    tableOrderStatusTone,
    tableOrderStatusBadge,
    tableOrderStatusIcon,
    tableOrderNextAction,
    tableOrderProgressSub,
    tableOrderPrimaryButtonText,
    tableOrderStatusTitle,
    tableOrderStatusHint,
    tableOrderTimeline,
    currentOrderItemCount,
    currentOrderItems,
    currentOrderMainItemText,
    pendingOrderCount,
    orderHistoryTotal,
    orderHistoryItemCount,
  }
}
