import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { joinByEntranceCode } from '@/api/auth'
import { saveCustomerSession, clearCustomerSession } from '@/utils/auth'
import { isDiningIdentityError } from '@/utils/dining'
import { reportError } from '@/utils/monitor'
import { savePendingSubmitIntent, restorePendingSubmitIntent, clearPendingSubmitIntent } from '@/utils/pendingSubmitIntent'
import { confirmationText, toastText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的下单 + 支付 + 待支付恢复 + 结账授权这一整条链路。这是全部
// 拆解里风险最高的一块——直接碰真金白银和订单记录，一旦哪个环节漏传状态，
// 轻则订单状态显示错，重则可能重复扣款或者顾客付了钱却看不到成功页。
//
// 没有再往下拆成更小的文件，是因为这些函数互相递归调用得很深（
// performSubmitOrder 调 confirmPay，confirmPay 调 recoverPendingPaymentResult，
// handleCheckoutAuth 同时调 continuePendingPaymentIntent 和 confirmPay），
// 硬拆只会把耦合从"同一个文件里的函数调用"变成"跨文件的回调参数"，可读性
// 不会变好，反而更容易在传参时漏传一个状态。保持它们在同一个模块里，用
// 闭包互相调用，跟原来在 menu.vue 里的调用关系完全一致。
//
// 所有逻辑跟原来在 menu.vue 里一字未改，只是把用到的页面状态都改成参数传入。
// ensureDiningSession/bindCurrentDiningParticipant/syncDiningOrders/
// normalizePaymentMode/persistDiningContext 相关的"拼桌身份"函数，以及
// refreshCustomerAuthState/saveMyOrders/startStatusPoll
// 这些来自别的组合式函数的方法，都是回调传入，不在这里重新实现。
//
// P0-B2a: successMemberValue 是 GET /v1/orders/my 的 member_value 权威结果
// （唯一 source，永远不在这里重新计算 savings/points），成功页奖励券也统一从
// 这里的 reward_coupon_status 派生——不再消费入会欢迎券兜底，那是另一套跟
// "本单支付奖励"无关的合同，保留在 WelcomeCouponSheet/useWelcomeCoupon 里。
//
// P0-B2b: 支付结果因为弱网/超时/切后台/被杀进程而进入"未知"，之后恢复对账
// 确认已支付，最终用户看到的必须跟正常支付成功一致（同一套 member_value/
// reward）。upsertPaidOrderResult（myOrders upsert，允许重复调用）和
// hydratePaidSuccessPresentation（成功页展示，显式传 id、cross-order 安全）
// 是从 _handlePaySuccess 里拆出来的两个可复用职责，recoverPendingPaymentResult
// 复用它们，而不是直接调用 _handlePaySuccess——后者还带着购物车/备注/优惠券/
// 幂等请求号这些"这一次结账流程结束了"的清理动作，恢复对账发生的时间点用户
// 完全可能已经在操作一个新的购物车，不能被这些清理动作误伤。是否安全清空
// 购物车，交给 applyRecoveryCartCleanup 用指纹比对 successItems 快照判断。
export function useCheckout({
  shopId, tableNo, diningSessionId, diningParticipantToken, diningClientId,
  orderNo, orderId, orderStatus, successItems, successTotal, successDiscount, successMemberValue, successPaymentMode,
  showCheckoutAuth, authorizing, authActionStatus, pendingPaymentIntent, paying, paymentFailed, paymentConfirming, paymentResultUnknown,
  payAmount, pendingOrderId, pendingSubmitRequestId,
  myOrders, showOrders, showCart, showSuccess, successPreserveDraft,
  ordering, tableSessionClosed, paymentMode,
  reminderRequested, earnedCoupon, cart, specCartItems, remark, selectedCouponId,
  totalPrice, cartItems, finalPrice, wechatPayAmount, isPrepayMode, canSubmitOrder,
  orderSuccessTemplateId, pickupReminderTemplateId,
  showMemberCheckoutChoice, memberChoiceJoining, memberCheckoutBenefitsNeedRefresh, isCustomerLoggedIn,
  wxLogin, ensureDiningSession, bindCurrentDiningParticipant, syncDiningOrders,
  normalizePaymentMode, refreshCustomerAuthState, saveMyOrders, startStatusPoll,
  clearDiningSessionStorage, refreshAvailableCoupons,
}) {
  const memberBenefitsRefreshPending = memberCheckoutBenefitsNeedRefresh || { value: false }
  // P0-15-01: keyed the same way as pendingPaymentStorageKey below -- tenant +
  // table + dining_session_id, never just tenant+table (table_no gets reused
  // by unrelated guest generations). Returns null when there's no valid
  // session yet, same contract as pendingPaymentStorageKey.
  const submitIntentScope = () => {
    const sessionId = diningSessionId?.value
    if (!sessionId) return null
    return { tenantId: shopId.value, tableNo: tableNo.value, sessionId }
  }

  // Restore is resolved once, up front, in performSubmitOrder (it needs the
  // whole record, not just the id -- see the payload-drift fix there). This
  // only mints a fresh id for the case performSubmitOrder has already
  // determined there's nothing to restore.
  const ensureSubmitRequestId = () => {
    if (!pendingSubmitRequestId.value) {
      pendingSubmitRequestId.value = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    }
    return pendingSubmitRequestId.value
  }

  const clearCurrentPendingSubmitIntent = () => {
    const scope = submitIntentScope()
    if (scope) clearPendingSubmitIntent(scope)
  }

  // A genuine network/timeout failure, as produced by api/request.js's `fail:`
  // branch, is a bare Error with no statusCode/code/bizCode -- those are only
  // ever set on a real HTTP response (see request.js: the 401/403 and generic
  // business-error branches both set error.statusCode/error.code, the fail:
  // branch never does). This is the one place server response and "the
  // request never got a response at all" are still distinguishable once the
  // error has already reached useCheckout.js.
  const isAmbiguousSubmitError = (err) => (
    err && err.statusCode === undefined && err.code === undefined && err.bizCode === undefined
  )

  const isCheckoutAuthError = (err) => {
    const code = String(err?.code || '')
    const statusCode = Number(err?.statusCode || 0)
    const message = String(err?.message || '')
    return [401, 403].includes(statusCode) || ['401', '403', 'NEED_LOGIN', 'member auth required'].includes(code) || message.includes('NEED_LOGIN')
  }

  const requireCheckoutAuth = () => {
    clearCustomerSession()
    refreshCustomerAuthState()
    if (!pendingPaymentIntent.value && !pendingOrderId.value) pendingPaymentIntent.value = createPaymentIntent()
    authActionStatus.value = 'idle'
    showCheckoutAuth.value = true
  }

  // P0-10: keyed by dining_session_id too, not just shop+table -- table_no gets
  // reused by unrelated guest generations over time, so a shop+table-only key
  // would let a later generation restore an earlier generation's pending-payment
  // order id into local state. Returns null when there's no valid session yet;
  // callers must treat that as "nothing to save/restore," never fall back to a
  // shop+table-only key.
  const pendingPaymentStorageKey = () => {
    const sessionId = diningSessionId?.value
    if (!sessionId) return null
    return 'pending_payment_order_' + shopId.value + '_' + tableNo.value + '_' + sessionId
  }

  const savePendingPaymentOrder = () => {
    if (!pendingOrderId.value) return
    const key = pendingPaymentStorageKey()
    if (!key) return
    try {
      uni.setStorageSync(key, JSON.stringify({
        orderId: pendingOrderId.value,
        orderNo: orderNo.value,
        payAmount: payAmount.value,
        total: payAmount.value,
        items: successItems.value,
        createdTs: Date.now(),
      }))
    } catch (e) {
      // 这份本地快照是"顾客支付到一半、小程序被强制退出"的兜底——存不进去
      // 不会立刻影响这一次支付，但下次冷启动就没有这份"我还欠一次支付"的
      // 记录了，值得报一下，不能悄悄丢掉。
      reportError('checkout.save_pending_payment', e)
    }
  }

  const restorePendingPaymentOrder = () => {
    if (pendingOrderId.value) return true
    const key = pendingPaymentStorageKey()
    if (!key) return false
    try {
      const raw = uni.getStorageSync(key)
      if (!raw) return false
      const record = JSON.parse(raw)
      if (!record?.orderId) return false
      pendingOrderId.value = String(record.orderId)
      orderNo.value = String(record.orderNo || record.orderId || '').slice(-4)
      payAmount.value = Number(record.payAmount || record.total || 0)
      successItems.value = Array.isArray(record.items) ? record.items : []
      successTotal.value = Number(record.total || record.payAmount || 0)
      return true
    } catch (e) {
      // 存储读出来的内容损坏/不是合法 JSON——理论上不该发生，一旦发生就意味着
      // "断线重连恢复待支付订单"这条安全网直接失效了，必须能看见。
      reportError('checkout.restore_pending_payment', e)
      return false
    }
  }

  const clearPendingPaymentOrder = () => {
    // 清不掉一个本地的"待支付"缓存 key 本身不影响这次流程——最多下次冷启动时
    // 多一次没必要的对账，够不上单独报错的门槛，这里是刻意留空，不是漏处理。
    // eslint-disable-next-line no-empty
    try { const key = pendingPaymentStorageKey(); if (key) uni.removeStorageSync(key) } catch (e) {}
    pendingOrderId.value = ''
    paymentFailed.value = false
    if (paymentConfirming) paymentConfirming.value = false
    if (paymentResultUnknown) paymentResultUnknown.value = false
  }

  const clearStalePrepayOrderForPayLater = () => {
    if (isPrepayMode.value || !pendingOrderId.value) return
    clearPendingPaymentOrder()
    pendingPaymentIntent.value = null
  }

  const isPaidOrSubmittedOrder = (order) => {
    const status = order?.status || ''
    const paymentStatus = order?.payment_status || ''
    const mode = normalizePaymentMode(order?.payment_mode || paymentMode.value)
    if (mode === 'prepay') return paymentStatus === 'paid'
    return paymentStatus === 'paid' || ['pending', 'paid', 'accepted', 'preparing', 'done', 'completed', 'settled'].includes(status)
  }

  const reconcileTerminalOrder = async (id, data, { showDetail = false } = {}) => {
    orderId.value = id
    orderStatus.value = data.status
    showSuccess.value = false
    pendingPaymentIntent.value = null
    // P0-B2b P0 cross-order 守卫：id 这里完全可能是调用方（比如
    // recoverPaymentResultById 用一个已经冻结好的 explicit id）传进来的一笔
    // 早先订单，而 pendingOrderId 这时候已经指向一笔更新的、真正还在等待
    // 支付的订单——绝不能因为对账了 A 的 terminal 结果，就把 B 的
    // pending-payment 标记（连带 paymentFailed/paymentConfirming/
    // paymentResultUnknown）也一起清掉。只有这次对账的订单确实还是当前
    // pendingOrderId 指向的那一笔时，才允许清。
    if (String(pendingOrderId.value) === String(id)) {
      clearPendingPaymentOrder()
    }
    // The table-session DTO is intentionally narrower than the order status DTO.
    // Sync first, then re-apply the authoritative late-payment attention so the
    // narrower snapshot cannot erase refundRequired from the local order card.
    await syncDiningOrders()
    const now = new Date()
    const existing = myOrders.value.find(o => String(o.id) === String(id))
    const patch = {
      status: data.status,
      paymentStatus: data.payment_status || 'unpaid',
      refundRequired: data.refund_required === true,
    }
    if (existing) Object.assign(existing, patch)
    else {
      myOrders.value.unshift({
        id,
        orderNo: orderNo.value || String(id).slice(-4),
        ...patch,
        items: successItems.value,
        total: successTotal.value || payAmount.value,
        createdAt: now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0'),
        createdTs: now.getTime(),
        table: tableNo.value,
        shop: shopId.value,
      })
    }
    saveMyOrders()
    showOrders.value = showDetail || showOrders.value
    if (data.refund_required === true) {
      uni.showToast({
        title: '订单已取消，付款已成功，请联系商家处理退款',
        icon: 'none',
        duration: 2600,
      })
    }
  }

  // P0-B2b: myOrders 只允许 upsert，绝不 unshift 第二次——同一个 order id 可能
  // 被正常支付确认和恢复对账各命中一次（甚至恢复本身也可能因为 onShow 重复
  // 触发），必须幂等。只负责"这笔已支付订单在订单列表里的事实"，不碰
  // showSuccess/cart 等任何跟"当前正在展示哪张成功页"或"购物车里有什么"
  // 相关的状态——那是 hydratePaidSuccessPresentation 和各自调用方自己的职责。
  const upsertPaidOrderResult = (id, data) => {
    const status = data.status || 'pending'
    const total = Number(data.total ?? payAmount.value)
    const now = new Date()
    const patch = {
      status,
      paymentStatus: data.payment_status || '',
      paymentMode: normalizePaymentMode(data.payment_mode || paymentMode.value),
      diningSessionId: diningSessionId.value || '',
      tableSessionId: diningSessionId.value || '',
    }
    if (data.pickup_no) patch.pickupNo = data.pickup_no
    const existing = myOrders.value.find(o => String(o.id) === String(id))
    if (existing) {
      Object.assign(existing, patch)
    } else {
      myOrders.value.unshift({
        id,
        orderNo: orderNo.value || String(id).slice(-4),
        items: successItems.value,
        total,
        createdAt: now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0'),
        createdTs: now.getTime(),
        table: tableNo.value,
        shop: shopId.value,
        pickupNo: data.pickup_no || '',
        ...patch,
      })
    }
    saveMyOrders()
    startStatusPoll(id)
  }

  // P0-B2b: 成功页展示唯一入口，正常支付和恢复对账共用同一份 authority——
  // member_value/reward 继续只透传给 applyAuthoritativeMemberReward，这里不
  // 重新判断一次。显式接收 id 而不是隐式读 pendingOrderId.value：调用方在
  // 这之后马上就会 clearPendingPaymentOrder()，届时 pendingOrderId 已经是空的。
  //
  // Cross-order 守卫：如果当前正展示的成功页（showSuccess=true）已经是别的
  // 订单，恢复对账必须整体是安全的 no-op——绝不能让一笔迟到的恢复对账，覆盖
  // 用户正在看的另一笔订单的成功页（P0-B2b 审计 section 23/24）。这个守卫只
  // 在 allowOverwrite=false（恢复路径的默认值）时生效——正常支付成功
  // （_handlePaySuccess 传 allowOverwrite:true）永远可以把这一次真实完成的
  // 支付变成新的当前成功页，跟原来的行为一致，不因为上一张成功页还没关掉
  // 就被挡住。同一笔订单重复命中时允许幂等刷新 member_value，但不重复重置
  // reminderRequested，避免抹掉用户已经点过的"提醒我"状态。
  const hydratePaidSuccessPresentation = (id, data, { allowOverwrite = false } = {}) => {
    const isDifferentOrderShowing = showSuccess.value && String(orderId.value) !== String(id)
    if (isDifferentOrderShowing && !allowOverwrite) {
      return { applied: false, freshOpen: false }
    }
    const freshOpen = !showSuccess.value || isDifferentOrderShowing
    orderId.value = id
    orderStatus.value = data.status || 'pending'
    successTotal.value = Number(data.total ?? payAmount.value)
    // 成功页文案要绑定"这一笔订单"实际的 payment_mode，不是页面当前的
    // paymentMode.value——恢复路径可能在展示一笔跟页面当前状态不同模式的
    // 旧订单，不能让文案跟着串到另一笔订单的模式上去。data 没带这个字段时
    // 才退回页面当前值，跟 upsertPaidOrderResult 里同样的兜底写法一致。
    if (successPaymentMode) successPaymentMode.value = normalizePaymentMode(data.payment_mode || paymentMode.value)
    applyAuthoritativeMemberReward(data.member_value || null)
    if (freshOpen) reminderRequested.value = false
    showSuccess.value = true
    return { applied: true, freshOpen }
  }

  // P0-B2b: 最小语义 fingerprint，只挑会改变"这是不是同一份购物车选择"的字段，
  // 忽略展示用的临时字段；用 JSON.stringify 而不是比较 Vue Proxy 引用/身份。
  const cartItemFingerprint = (item) => JSON.stringify({
    id: item.id,
    qty: item.qty,
    price: item.price,
    specKey: item.specKey || '',
    itemRemark: item.itemRemark || '',
    specifications: item.specifications || [],
    extras: item.extras || [],
  })

  // 当前购物车是否仍然就是这笔已支付订单提交时的那份快照（successItems）。
  // 只有完全一致才能证明用户在 UNKNOWN 之后没有再改过购物车。
  const isCurrentCartSameAsSubmittedSnapshot = () => {
    const current = cartItems.value
    const snapshot = Array.isArray(successItems.value) ? successItems.value : []
    if (current.length !== snapshot.length) return false
    const sortedCurrent = current.map(cartItemFingerprint).sort()
    const sortedSnapshot = snapshot.map(cartItemFingerprint).sort()
    return sortedCurrent.every((fp, idx) => fp === sortedSnapshot[idx])
  }

  // P0-B2b P0 约束：恢复到的这笔支付可能是很久以前提交的，用户很可能已经在
  // UNKNOWN 之后继续加了新东西到购物车——不能像正常支付成功那样无条件清空。
  // 只有指纹证明"购物车原封不动就是刚刚已支付的这些东西"时，才按正常成功页
  // 的方式清空；否则整体原样保留，交给 successPreserveDraft 让 UI 层提示用户
  // 自己确认，本阶段不做任何自动增删（数据丢失 fail-closed，见 P0-B2b 审计
  // section 14）。
  const applyRecoveryCartCleanup = () => {
    if (!isCurrentCartSameAsSubmittedSnapshot()) {
      if (successPreserveDraft) successPreserveDraft.value = true
      return
    }
    cart.value = {}
    specCartItems.value = []
    selectedCouponId.value = null
    remark.value = ''
    pendingSubmitRequestId.value = ''
    if (successPreserveDraft) successPreserveDraft.value = false
  }

  // P0-B2b P0 fix: 对一个显式给定的 order id 做支付结果核对，不读、不依赖
  // 共享的 pendingOrderId.value——调用方（不管是下面的公开
  // recoverPendingPaymentResult，还是 confirmPay 支付异常后的 catch）必须
  // 自己在异步窗口打开之前把 id 冻结好再传进来。这是 P0-B2a/P0-B2b 唯一一套
  // paid/terminal reconciliation authority，upsertPaidOrderResult/
  // hydratePaidSuccessPresentation/applyRecoveryCartCleanup/
  // applyAuthoritativeMemberReward/reconcileTerminalOrder 全部原样复用，不
  // 写第二套。
  const recoverPaymentResultById = async (id, { showDetail = false, presentSuccess = false } = {}) => {
    if (!id) return false
    try {
      const res = await getOrderStatus(id, diningParticipantToken.value)
      const data = res?.data || {}
      if (['cancelled', 'rejected'].includes(data.status)) {
        await reconcileTerminalOrder(id, data, { showDetail })
        return false
      }
      if (isPaidOrSubmittedOrder(data)) {
        pendingPaymentIntent.value = null

        const paidData = { ...data, total: payAmount.value }
        upsertPaidOrderResult(id, paidData)

        // 同一订单的成功页已经开着（正常支付和这次恢复撞上了，或者恢复本身
        // 被重复触发）——幂等刷新，不重复弹、不重复清购物车。
        const alreadyShowingSameOrder = showSuccess.value && String(orderId.value) === String(id)
        if (presentSuccess || alreadyShowingSameOrder) {
          const { applied, freshOpen } = hydratePaidSuccessPresentation(id, paidData)
          // applied=false 只可能是 cross-order 守卫拦下了（另一笔订单的成功页
          // 正开着）——这种情况下连 showCart/showCheckoutAuth 都不能碰，用户
          // 当前在做的事情跟这次恢复完全无关，必须整体是 no-op。
          if (applied) {
            showCart.value = false
            showCheckoutAuth.value = false
            if (freshOpen) applyRecoveryCartCleanup()
          }
        } else {
          // 用户已经不在这笔支付的上下文里了（后台迟到恢复、且当时并不是
          // "支付结果未知"那种主动等待态）——只非阻塞提示，不强弹成功页，
          // 不碰 showCart/showCheckoutAuth 这些当前可能正在被用户使用的 UI
          // 状态，不展示"本单已省 X 元"这类需要 member_value 的具体数值
          // （P0-B2b 审计 section 22：避免另建一套 display authority）。
          uni.showToast({ title: '上一笔订单已支付成功', icon: 'none', duration: 2000 })
        }

        // P0-B2b P0 cross-order 守卫：只清跟这次恢复严格同一个 id 的 pending
        // 标记。pendingOrderId 完全可能已经被另一路并发的恢复/正常支付清成
        // 空字符串，或者用户在这中间已经提交了一笔全新的订单、pendingOrderId
        // 指向的是那笔新订单——两种情况都绝不能被这次对账动到，否则会把一笔
        // 真正还待支付的新订单标记误清掉。
        if (String(pendingOrderId.value) === String(id)) {
          clearPendingPaymentOrder()
        }
        await syncDiningOrders()
        showOrders.value = showDetail || showOrders.value
        return true
      }
      return false
    } catch (e) {
      // 底层网络失败本身已经在 api/request.js 里报过一次了，这里单独再报一次
      // 是因为"对账失败"这件事本身有独立的排查价值——能单独统计"待支付订单
      // 恢复失败率"，不用从一堆通用网络错误里去猜。
      reportError('checkout.recover_pending_payment', e)
      return false
    }
  }

  let recoveringPayment = false
  const recoverPendingPaymentResult = async ({ showDetail = false, presentSuccess = false } = {}) => {
    if (recoveringPayment) return false
    restorePendingPaymentOrder()
    const id = pendingOrderId.value
    if (!id) return false
    recoveringPayment = true
    try {
      return await recoverPaymentResultById(id, { showDetail, presentSuccess })
    } finally {
      recoveringPayment = false
    }
  }

  const createPaymentIntent = () => ({
    merchantId: shopId.value,
    tableId: tableNo.value,
    cartSnapshot: cartItems.value.map(item => ({ id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specKey: item.specKey || '' })),
    couponId: selectedCouponId.value || null,
    orderRemark: remark.value.trim(),
    payableAmount: wechatPayAmount.value,
    requestId: 'pay_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
    createdAt: Date.now(),
  })

  const resolveRequiredMemberBenefits = async () => {
    memberBenefitsRefreshPending.value = true
    await refreshAvailableCoupons({ required: true, forceBest: true })
    memberBenefitsRefreshPending.value = false
  }

  // P0-A: 会员是否加入是可选项，MEMBERSHIP_IS_OPTIONAL=YES——只有还没登录会员
  // 的顾客点结算，才弹出"加入会员并继续 / 直接支付"的选择层；已经是会员的、
  // 或者已经有待支付订单要恢复的（P0-9：绝不能把新会员的券偷偷套到旧订单上），
  // 都走原来的路径不受影响。
  const goCheckout = () => {
    if (ordering.value || paying.value || authorizing.value || memberChoiceJoining.value) return
    if (!canSubmitOrder.value) {
      uni.showToast({
        title: tableSessionClosed.value
          ? toastText.tableSessionEnded
          : (tableNo.value ? confirmationText.unavailable : confirmationText.tableMissing),
        icon: 'none',
      })
      return
    }
    clearStalePrepayOrderForPayLater()
    if (pendingOrderId.value) return confirmPay()
    if (memberBenefitsRefreshPending.value) {
      retryRequiredMemberBenefitsAndCheckout()
      return
    }
    if (showMemberCheckoutChoice && !isCustomerLoggedIn.value) {
      showMemberCheckoutChoice.value = true
      return
    }
    submitOrder()
  }

  const cancelCheckoutAuth = () => {
    if (authorizing.value) return
    showCheckoutAuth.value = false
  }

  // 关掉选择层，回到已经在下面展示着的购物车确认单——不创建订单、不清空购物
  // 车、不强制注册，顾客随时能再点结算重新打开这一层。
  const cancelMemberCheckoutChoice = () => {
    if (memberChoiceJoining.value) return
    showMemberCheckoutChoice.value = false
  }

  // 保留今天现有的匿名结算合同：不强制手机号、不强制注册、不强制会员协议。
  const checkoutAsGuest = () => {
    if (memberChoiceJoining.value || ordering.value || paying.value) return
    if (memberBenefitsRefreshPending.value) {
      retryRequiredMemberBenefitsAndCheckout()
      return
    }
    showMemberCheckoutChoice.value = false
    submitOrder()
  }

  const retryRequiredMemberBenefitsAndCheckout = async () => {
    if (memberChoiceJoining.value || ordering.value || paying.value || authorizing.value) return false
    memberChoiceJoining.value = true
    try {
      await resolveRequiredMemberBenefits()
      showMemberCheckoutChoice.value = false
      return await submitOrder()
    } catch (err) {
      uni.showToast({ title: err?.message || toastText.memberBenefitsLoadFailed, icon: 'none' })
      return false
    } finally {
      memberChoiceJoining.value = false
    }
  }

  // 结算前"加入会员并继续"——跟 handleCheckoutAuth（授权失效后的被动补救）
  // 是两条不同的路径，不能合并：这里发生在 createOrder 之前，join 成功后必须
  // 依次完成 保存会员会话 → 绑定拼桌身份 → 刷新会员登录态 → 刷新全部未用券 →
  // 选出本单最优券，全部落定以后才调用 submitOrder()去冻结提交快照——一旦
  // performSubmitOrder 里的 savePendingSubmitIntent 发生，payload 里的
  // coupon_id 就再也不能被这条路径改变了，顺序不能反。
  const joinMemberAndCheckout = async (event) => {
    if (memberChoiceJoining.value || ordering.value || paying.value || authorizing.value) return
    // 已经有一笔待支付订单在等着恢复，那是另一套安全合同（见 P0-10 的
    // pendingPaymentStorageKey 场景）——绝不能把这次新加入会员选到的券，
    // 悄悄套用到那笔已经建好的旧订单上，也不重新定价。
    if (pendingOrderId.value) {
      showMemberCheckoutChoice.value = false
      return
    }
    const phoneCode = event?.detail?.code || event?.detail?.phoneCode || ''
    if (!phoneCode) {
      uni.showToast({ title: toastText.authIncomplete, icon: 'none' })
      return
    }
    memberChoiceJoining.value = true
    try {
      const code = await wxLogin()
      const res = await joinByEntranceCode({
        scene: uni.getStorageSync('entrance_scene') || '',
        tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
        table_no: tableNo.value || uni.getStorageSync('table_no') || '',
        code,
        phone_code: phoneCode,
        agreement_accepted: true,
        invite_code: uni.getStorageSync('invite_code') || '',
      }, { authRedirect: false })
      if (res.code !== 200) {
        uni.showToast({ title: res?.msg || toastText.joinMemberFailed, icon: 'none', duration: 1200 })
        return
      }
      uni.removeStorageSync('invite_code')
      saveCustomerSession(res.data || {})
      await bindCurrentDiningParticipant()
      refreshCustomerAuthState()
      // 老会员可能已经有好几张券、新人也可能已经被后端去重过——join 接口
      // response 里那一张券不能当成唯一真相，必须重新拉一次全量未用券。
      // couponPickerList（refreshAvailableCoupons 内部用的排序）已经改成按
      // "实际能减多少钱"选最优，不是按券面值，PERCENT 类型也能选对。
      await resolveRequiredMemberBenefits()
      showMemberCheckoutChoice.value = false
      await submitOrder()
    } catch (err) {
      uni.showToast({ title: err?.message || toastText.authIncomplete, icon: 'none' })
    } finally {
      memberChoiceJoining.value = false
    }
  }

  const continuePendingPaymentIntent = async () => {
    clearStalePrepayOrderForPayLater()
    if (!pendingPaymentIntent.value && !pendingOrderId.value) pendingPaymentIntent.value = createPaymentIntent()
    if (pendingOrderId.value) return confirmPay()
    return submitOrder()
  }

  const handleCheckoutAuth = async (event) => {
    if (authorizing.value || ordering.value || paying.value) return
    const phoneCode = event?.detail?.code || event?.detail?.phoneCode || ''
    if (!phoneCode) return uni.showToast({ title: toastText.authIncomplete, icon: 'none' })
    authorizing.value = true
    authActionStatus.value = 'authorizing'
    try {
      const code = await wxLogin()
      const res = await joinByEntranceCode({
        scene: uni.getStorageSync('entrance_scene') || '',
        tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
        table_no: tableNo.value || uni.getStorageSync('table_no') || '',
        code,
        phone_code: phoneCode,
        agreement_accepted: true,
        invite_code: uni.getStorageSync('invite_code') || '',
      }, { authRedirect: false })
      if (res.code !== 200) {
        authActionStatus.value = 'idle'
        uni.showToast({ title: res?.msg || toastText.joinMemberFailed, icon: 'none', duration: 1200 })
        return
      }
      uni.removeStorageSync('invite_code')
      saveCustomerSession(res.data || {})
      await bindCurrentDiningParticipant()
      refreshCustomerAuthState()
      const scope = submitIntentScope()
      const recoveringFrozenSubmitIntent = Boolean(scope && restorePendingSubmitIntent(scope).status === 'found')
      // createOrder 尚未成功、只是旧 customer_token 被明确拒绝时，授权后的会员
      // 身份可能带来不同的 UNUSED 券。必须先刷新并确定最终券，再让下面的提交
      // 重新冻结；已有 pendingOrderId 的支付恢复则绝不能在这里改价。
      if (!pendingOrderId.value && !recoveringFrozenSubmitIntent) await resolveRequiredMemberBenefits()
      authActionStatus.value = 'submitting'
      const ok = await continuePendingPaymentIntent()
      if (ok) {
        pendingPaymentIntent.value = null
        showCheckoutAuth.value = false
      } else {
        authActionStatus.value = 'idle'
      }
    } catch (err) {
      authActionStatus.value = 'idle'
      uni.showToast({ title: err.message || toastText.authIncomplete, icon: 'none' })
    } finally {
      authorizing.value = false
      if (!ordering.value && !paying.value && authActionStatus.value !== 'idle') authActionStatus.value = 'idle'
    }
  }

  // 支付前申请点餐成功 + 取餐提醒授权（一次性额度，拒绝也不阻断下单）。
  const requestOrderSubscribeMessages = async () => {
    const ids = [
      orderSuccessTemplateId?.value,
      pickupReminderTemplateId?.value,
    ].filter(Boolean).slice(0, 3)
    if (!ids.length) return
    await new Promise((resolve) => {
      try {
        uni.requestSubscribeMessage({
          tmplIds: ids,
          complete: resolve,
          fail: resolve,
        })
      } catch (e) {
        resolve()
      }
    })
  }

  // performSubmitOrder 拆出来是为了让"本桌身份失效，重建后自动重试一次"这条路径能
  // 递归调用自己而不撞上 submitOrder 自己的 ordering.value 重入锁（锁在整个下单+支付
  // 期间一直是 true，递归调用外层 submitOrder 会被这把锁直接挡回来）。
  const performSubmitOrder = async (isRetry = false) => {
    let replayingFrozenIntent = false
    try {
      const sessionReady = await ensureDiningSession()
      if (!sessionReady || tableSessionClosed.value) {
        throw new Error(tableSessionClosed.value ? toastText.tableSessionEnded : toastText.tableSessionUnavailable)
      }
      // 必须在用户点击提交的手势链里调用，否则微信不会弹授权框。
      await requestOrderSubscribeMessages()

      const submitScope = submitIntentScope()
      const restoreResult = submitScope ? restorePendingSubmitIntent(submitScope) : { status: 'missing' }
      replayingFrozenIntent = restoreResult.status === 'found'

      // P0-15 closure: a record exists for this scope but can't be read back
      // reliably (corrupt JSON, missing its requestId) -- this must NOT be
      // treated the same as "nothing pending." A real prior attempt under
      // this scope may still be genuinely unresolved server-side; minting a
      // fresh identity and sending under it risks the exact P0-15-01
      // duplicate-order failure. Fail closed instead.
      if (restoreResult.status === 'corrupt') {
        const corruptErr = new Error(toastText.submitIntentUnrecoverable)
        corruptErr.__corruptIntent = true
        throw corruptErr
      }

      let payload
      if (restoreResult.status === 'found') {
        // P0-15 closure Gap B: an earlier attempt under this exact scope is
        // still unresolved -- resend its FROZEN canonical payload, never a
        // payload rebuilt from the live cart (which may have changed since).
        // Only non-business context (participant_token/client_id) is re-read
        // fresh; everything the P0-04 server fingerprint actually keys on
        // (table/dining_session_id/coupon_id/remark/items) comes from the
        // frozen snapshot untouched.
        const snap = restoreResult.record.snapshot || {}
        payload = {
          ...snap,
          participant_token: diningParticipantToken.value || undefined,
          client_id: diningClientId.value || undefined,
          request_id: restoreResult.record.requestId,
        }
        pendingSubmitRequestId.value = restoreResult.record.requestId
      } else {
        payload = {
          table: tableNo.value,
          shop: shopId.value,
          total: totalPrice.value,
          remark: remark.value.trim() || undefined,
          coupon_id: selectedCouponId.value || undefined,
          dining_session_id: diningSessionId.value || undefined,
          participant_token: diningParticipantToken.value || undefined,
          client_id: diningClientId.value || undefined,
          request_id: ensureSubmitRequestId(),
          // P0-04 remark reconciliation: item_remark must come from the cart line's real
          // itemRemark field (set by useSpecSheet's confirmSpec, spec'd items only) --
          // never re-derived from orderName/name, which are display-only folded text.
          // Sent explicitly (even as '') for spec'd items so the server trusts this field
          // instead of falling back to legacy name-parsing; omitted for simple items,
          // which have no remark concept at all (no UI path to enter one).
          items: cartItems.value.map((item) => ({ dish_id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specifications: item.specifications && item.specifications.length ? item.specifications : undefined, extras: item.extras && item.extras.length ? item.extras : undefined, item_remark: item.itemRemark !== undefined ? item.itemRemark : undefined })),
        }
        // P0-15-01: persist the submit intent BEFORE the network call, not after --
        // if the app process dies between the request being sent and the response
        // arriving, this is the only record that survives to make the next retry
        // (a fresh page instance) reuse the same request_id instead of minting a
        // new one. No participant_token/credential is stored -- retries always
        // re-read that fresh from the current session context (see payload above).
        //
        // P0-15 closure Gap A: if this write fails, we have no durable record
        // of the identity we're about to send under -- do NOT send the
        // mutation at all. A silently-unrecorded in-flight request is exactly
        // the P0-15-01 failure mode, just reached via a storage fault instead
        // of a process kill.
        if (submitScope) {
          const persisted = savePendingSubmitIntent({
            ...submitScope,
            requestId: payload.request_id,
            snapshot: { table: payload.table, shop: payload.shop, total: payload.total, remark: payload.remark, coupon_id: payload.coupon_id, dining_session_id: payload.dining_session_id, items: payload.items },
          })
          if (!persisted) {
            const saveErr = new Error(toastText.submitIntentSaveFailed)
            saveErr.__saveFailed = true
            throw saveErr
          }
        }
      }
      let res
      try {
        res = await createOrder(payload, { authRedirect: false })
      } catch (submitErr) {
        // Tag right here, at the one call site this ambiguity classification
        // is actually about -- every other throw in this function (session
        // not ready, empty pendingOrderId after a real response, etc.) is a
        // definitive, locally-known condition and must keep its own specific
        // message, even though some of those errors also happen to carry no
        // statusCode/code (they were never network errors to begin with).
        if (isAmbiguousSubmitError(submitErr)) submitErr.__ambiguousSubmit = true
        throw submitErr
      }
      const data = res?.data || {}
      pendingOrderId.value = String(data.id || data.order_id || '')
      // Order identity is now server-confirmed -- the submit intent this
      // request_id was tracking is resolved. Whether payment is still needed is
      // a separate, later lifecycle (see savePendingPaymentOrder below).
      clearCurrentPendingSubmitIntent()
      paymentFailed.value = false
      orderNo.value = String(data.order_no || data.id || '').slice(-4)
      successItems.value = cartItems.value.map(i => ({ ...i }))
      successDiscount.value = Number(data.discount_amount ?? 0)
      payAmount.value = Number(data.pay_amount ?? data.total ?? finalPrice.value)
      paymentMode.value = normalizePaymentMode(data.payment_mode)
      if (!pendingOrderId.value) throw new Error(toastText.createOrderFailed)
      if (data.need_payment !== false) {
        savePendingPaymentOrder()
        return await confirmPay()
      }
      // P0-B2b race fix: capture the id synchronously, right here, before
      // anything else can run -- _handlePaySuccess no longer trusts
      // pendingOrderId.value internally (see its own definition below).
      const completedOrderId = pendingOrderId.value
      _handlePaySuccess(completedOrderId, { ...data, total: payAmount.value, status: data.status || 'pending' })
      pendingPaymentIntent.value = null
      return true
    } catch (err) {
      // P0-04: same request_id retried with genuinely different cart content --
      // server fails closed instead of silently replaying stale content (or,
      // worse, silently creating a second order). Must be checked BEFORE
      // isDiningIdentityError below: both use code===409, but they mean
      // completely different things, and this one must never fall into that
      // branch's "rebuild identity and blindly retry" behavior -- retrying
      // blindly here would just hit the exact same conflict again.
      // Never clears pendingSubmitRequestId or generates a new key: the
      // existing order this key already produced is what we bind to and
      // recover, reusing the same paths a normal pending-payment recovery
      // already uses (never a second order-recovery UI).
      if (err?.bizCode === 'IDEMPOTENCY_CONFLICT' && err?.data?.existing_order_id) {
        pendingOrderId.value = String(err.data.existing_order_id)
        // Same reasoning as the direct-success path above: the server has told
        // us a real Order identity exists for this request_id, so the submit
        // intent is resolved regardless of which recovery branch runs next.
        clearCurrentPendingSubmitIntent()
        orderNo.value = String(err.data.existing_order_no || err.data.existing_order_id).slice(-4)
        paymentMode.value = normalizePaymentMode(err.data.payment_mode)
        if (err.data.need_payment) {
          return await confirmPay()
        }
        // 用户刚刚主动提交，服务端告知这个 request_id 早就有一笔已支付订单——
        // 跟上面两处 confirmPay 里的核对同一个道理，属于用户仍在等这笔支付
        // 结果的场景，发现已支付要展示完整成功页。
        const recovered = await recoverPendingPaymentResult({ showDetail: true, presentSuccess: true })
        if (recovered) return true
        uni.showToast({ title: toastText.submitOrderFailed, icon: 'none' })
        return false
      }
      // 本桌匿名身份失效（后端统一返回 409）不是会员登录问题，静默重建身份后自动重试
      // 一次；仍失败才走下面的兜底提示，不会弹"继续支付/授权"这种会员专属的措辞。
      if (!isRetry && isDiningIdentityError(err)) {
        const rebuilt = await ensureDiningSession(true)
        if (rebuilt) return performSubmitOrder(true)
      }
      // P0-10-05: rebuild-and-retry didn't recover (or this was already a retry) --
      // the cached dining_session_id/participant_token are genuinely stale (most
      // likely this table turned over to a new guest generation while this page
      // sat open) and must not be left behind for the next resume to trust again.
      // Deliberately NOT markSessionClosed: that also sets tableSessionClosed=true,
      // which is specifically wrong here (see the comment below) -- this only
      // invalidates the cache, it doesn't claim "本桌用餐已结束".
      if (isDiningIdentityError(err) && clearDiningSessionStorage) {
        clearDiningSessionStorage()
        diningParticipantToken.value = ''
        // The scope (dining_session_id) this pending intent was tracking is
        // itself being invalidated -- P0-10: never let a resumed page replay
        // a stale session's request_id into whatever session comes next.
        clearCurrentPendingSubmitIntent()
      }
      if (isCheckoutAuthError(err)) {
        // 401/403/NEED_LOGIN 是服务端已经明确拒绝本次建单的确定性结果，不是
        // "请求可能已经落库"的弱网未知态。旧 token 下冻结的 coupon_id 不能在
        // 重新授权后继续重放；同时丢弃本次未被服务端接受的 request_id，让授权
        // 成功后的提交重新冻结当时已刷新的券与购物车快照。
        if (!replayingFrozenIntent) {
          clearCurrentPendingSubmitIntent()
          pendingSubmitRequestId.value = ''
        }
        requireCheckoutAuth()
        return false
      }
      // P0-15 closure: a definitive business rejection (server actually
      // responded with a real error -- dish unavailable, price stale, store
      // closed, etc. -- confirmed no order was created) means the frozen
      // payload this request_id was tracking is now moot. Clear it so the
      // NEXT attempt is free to send a genuinely corrected cart -- without
      // this, the payload-freeze fix above (Gap B) would otherwise trap the
      // user resending the same rejected payload forever. Deliberately
      // excludes: ambiguous (must stay frozen, that's the whole point of the
      // freeze), dining-identity (already cleared above, different scope
      // concern), corrupt-record and save-failure (nothing of this attempt
      // was ever durably recorded to begin with -- clearing here could wipe
      // out a genuine still-unresolved EARLIER record instead).
      if (!isDiningIdentityError(err) && !err?.__ambiguousSubmit && !err?.__corruptIntent && !err?.__saveFailed) {
        clearCurrentPendingSubmitIntent()
      }
      const rawMsg = err?.message || ''
      // 409 /「本桌身份」可恢复：只提示重新扫码，绝不能标成 tableSessionClosed
      // （否则会伪装成「本桌用餐已结束」，且阻断后续 ensureDiningSession）。
      // 只有明确的会话结束文案才关桌。
      if (
        !isDiningIdentityError(err)
        && (rawMsg.includes('用餐已结束') || rawMsg.includes('本桌已结束') || rawMsg.includes('会话已关闭'))
      ) {
        tableSessionClosed.value = true
      }
      // P0-15-02: a genuine network/timeout failure means the outcome is
      // UNKNOWN, not FAILED -- the request may well have reached and been
      // committed by the server. This must take priority over the generic
      // "submit failed" copy (it does NOT apply to isDiningIdentityError,
      // which already has its own specific, accurate messaging above).
      const msg = isDiningIdentityError(err)
        ? (rawMsg || toastText.tableSessionUnavailable)
        : (err?.__ambiguousSubmit ? toastText.submitOrderUnknown : (rawMsg || toastText.submitOrderFailed))
      uni.showToast({ title: String(msg).slice(0, 30), icon: 'none' })
      return false
    }
  }

  const submitOrder = async () => {
    if (ordering.value || paying.value) return false
    ordering.value = true
    if (showCheckoutAuth.value) authActionStatus.value = 'submitting'
    try {
      return await performSubmitOrder()
    } finally {
      ordering.value = false
    }
  }

  // P0-B2b: 正常支付成功路径。id 必须由调用方显式传入，本函数内部绝不读
  // pendingOrderId.value——normal confirmation 的 requestPayment/
  // getOrderStatus 轮询跟并发的 recoverPendingPaymentResult（比如 onShow
  // 后台恢复）完全可能撞在一起：如果恢复先一步确认了同一笔订单已支付并调用
  // 了 clearPendingPaymentOrder()，这里再读 pendingOrderId.value 就会读到
  // 空字符串，产生一个 id 是空字符串的 myOrders 行/成功页。所有调用方都必须
  // 在自己那次异步操作开始之前就把 id 冻结成局部变量，而不是在这个函数执行
  // 的这一刻才去读共享的 pendingOrderId ref。
  //
  // 这里的购物车/备注/优惠券/幂等请求号清理保持无条件（P0-B2b 审计
  // section 9：正常支付成功的收尾行为不允许变化），跟恢复路径那套"先比对
  // 指纹再决定要不要清"的 applyRecoveryCartCleanup 是两码事，不合并。
  const _handlePaySuccess = (id, data) => {
    if (!id) return false
    showCart.value = false
    if (successPreserveDraft) successPreserveDraft.value = false
    upsertPaidOrderResult(id, data)
    hydratePaidSuccessPresentation(id, data, { allowOverwrite: true })
    cart.value = {}
    specCartItems.value = []
    selectedCouponId.value = null
    remark.value = ''
    pendingSubmitRequestId.value = ''
    clearPendingPaymentOrder()
    syncDiningOrders().catch(() => {})
    return true
  }

  // P0-B2a: 成功页会员价值/奖励券唯一 authority 是 GET /v1/orders/my 的
  // member_value——status/savings/points 原样透传给 successMemberValue，前端
  // 不重新计算任何金额或积分。reward_coupon_status 只在 member_value.status
  // 本身就是 "available" 时才有意义——status 是总闸门：not_applicable/
  // pending/unavailable 下即使 reward_coupon_status 恰好是 "issued"（历史
  // 快照残留、或该笔订单本身就有别的 invariant 问题），也一律不构造
  // earnedCoupon，因为这笔订单的会员事实本身还没有被判定为可信。只有
  // status === "available" 且 reward_coupon_status === "issued" 且真的带着
  // 券对象，才展示服务端真实发放的券；其余一律清空 earnedCoupon，不回退本地
  // 欢迎券（那是入会 onboarding 的合同，跟"这一单有没有拿到支付奖励"是两回
  // 事，混用会把欢迎券冒充成本单奖励——P0-B2 审计发现的那个 bug）。
  const applyAuthoritativeMemberReward = (memberValue) => {
    if (successMemberValue) successMemberValue.value = memberValue || null
    if (memberValue?.status !== 'available') {
      earnedCoupon.value = null
      return
    }
    const coupon = memberValue?.reward_coupon
    if (memberValue?.reward_coupon_status !== 'issued' || !coupon) {
      earnedCoupon.value = null
      return
    }
    earnedCoupon.value = {
      couponId: coupon.id || '',
      amount: Number(coupon.value ?? coupon.amount ?? 0),
      threshold: Number(coupon.min_amount ?? coupon.threshold ?? 0),
      // 后端给的是绝对过期时间 expired_at，不是相对天数，
      // 直接存成 expire_time 方便复用下面的 couponValidityText。
      expire_time: coupon.expired_at || '',
      name: coupon.name || '优惠券',
      isSecondOrder: Boolean(coupon.is_second_order),
    }
  }

  // P0-B2a: free 订单的 pay 响应（createWxPayOrder 的 free 分支）复用
  // serialize_order，没有 member_value 字段——支付/下单成功这个事实必须先
  // 正常展示，再用已有的 GET /orders/my 补一次权威会员价值。查询失败/超时/
  // 慢，或者顾客这期间已经关掉成功页、切去别的订单，都只是"不展示会员价值"，
  // 绝不能让这次补充查询反过来影响已经成立的支付成功结果。
  const fetchFreeOrderMemberValue = async (id) => {
    try {
      const res = await getOrderStatus(id, diningParticipantToken.value)
      const d = res?.data || {}
      if (showSuccess.value && String(orderId.value) === String(id)) {
        applyAuthoritativeMemberReward(d.member_value || null)
      }
    } catch (e) {
      // 保持 _handlePaySuccess 里已经置好的"暂不展示会员价值"安全态，不重试、
      // 不报错到界面——免单这笔钱本身已经成功，不因为一次权益查询失败降级。
    }
  }

  const waitForBackendPaymentConfirmation = async (id) => {
    if (!id) return false
    if (paymentConfirming) paymentConfirming.value = true
    if (paymentResultUnknown) paymentResultUnknown.value = false
    try {
      for (let attempt = 0; attempt < 6; attempt++) {
        if (attempt > 0) {
          await new Promise((resolve) => setTimeout(resolve, 900))
        }
        try {
          const res = await getOrderStatus(id, diningParticipantToken.value)
          const data = res?.data || {}
          if (['cancelled', 'rejected'].includes(data.status)) {
            await reconcileTerminalOrder(id, data)
            return false
          }
          if (data.payment_status === 'paid') {
            // P0-B2b race fix: `id` is this call's own parameter, captured by
            // the caller before this loop's awaits ever started -- it can't
            // have been clobbered by a concurrent recovery clearing
            // pendingOrderId.value out from under us.
            _handlePaySuccess(id, { ...data, total: payAmount.value })
            if (paymentResultUnknown) paymentResultUnknown.value = false
            return true
          }
        } catch (e) {
          reportError('checkout.confirm_backend_payment', e)
        }
      }
      if (paymentResultUnknown) paymentResultUnknown.value = true
      uni.showToast({ title: '支付结果确认中，请勿重复支付', icon: 'none', duration: 1800 })
      return false
    } finally {
      if (paymentConfirming) paymentConfirming.value = false
    }
  }

  const confirmPay = async () => {
    if (paying.value || !pendingOrderId.value) return false
    paying.value = true
    paymentFailed.value = false
    // P0-B2b P0 fix: 声明在 try 外面，这样 catch 里也能读到——
    // createWxPayOrder/uni.requestPayment 这些真正的异步支付动作期间，一旦
    // 抛出/reject，catch 必须仍然能核对这笔具体订单的服务端 truth，而不是
    // 重新去读这时候可能已经被并发恢复清空的 pendingOrderId.value。
    let paymentOrderId = ''
    try {
      // 待支付恢复等只走 confirmPay 的路径，也要再申请一次（已授权时微信通常不再弹框）。
      await requestOrderSubscribeMessages()
      // P0-B2b: 用户主动点了去支付，正在核对是不是已经支付过——这就是"用户
      // 仍在这笔支付的上下文里"，发现已支付必须直接展示完整成功页，不是只
      // 做后台对账。
      if (await recoverPendingPaymentResult({ presentSuccess: true })) return true

      // P0-B2b P0 fix: precheck 没能解决这笔订单——从这里开始，接下来还有
      // createWxPayOrder/uni.requestPayment 这些真正的异步支付动作，每一个
      // await 都是并发的 onShow/后台恢复可能抢先 clearPendingPaymentOrder 的
      // 窗口。这笔订单的 identity 就此冻结成外层变量，整条支付链（包括下面
      // 的 catch）往后绝不再读 pendingOrderId.value。
      paymentOrderId = pendingOrderId.value
      if (!paymentOrderId) return false

      if (paymentResultUnknown?.value) {
        return await waitForBackendPaymentConfirmation(paymentOrderId)
      }
      if (showCheckoutAuth.value) authActionStatus.value = 'paying'
      let jsCode = ''
      if (!uni.getStorageSync('customer_token')) {
        jsCode = await wxLogin()
      }
      const res = await createWxPayOrder(paymentOrderId, false, { authRedirect: false, js_code: jsCode, participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') })
      const data = res?.data || {}

      if (data.free) {
        // _handlePaySuccess/fetchFreeOrderMemberValue 都用上面冻结好的
        // paymentOrderId，不再单独重新读一次 pendingOrderId.value。
        _handlePaySuccess(paymentOrderId, data)
        pendingPaymentIntent.value = null
        fetchFreeOrderMemberValue(paymentOrderId)
        return true
      }

      const p = data.pay_params
      if (!p) {
        throw new Error('支付参数缺失，请重新下单')
      }

      await uni.requestPayment({
        provider: 'wxpay',
        timeStamp: p.timeStamp,
        nonceStr: p.nonceStr,
        package: p.package,
        signType: p.signType || 'RSA',
        paySign: p.paySign,
      })

      // P0-B2a: waitForBackendPaymentConfirmation 读到的就是 GET /v1/orders/my
      // 本身，member_value 已经在那次响应里——_handlePaySuccess 会直接消费它，
      // 不需要再单独轮询一次奖励券（P0-B1 上线后 reward 快照与 member_value
      // 已经同一次读取里权威可读，不再有"支付成功那一刻奖励还没落库"的旧合同）。
      const confirmed = await waitForBackendPaymentConfirmation(paymentOrderId)
      if (confirmed) {
        pendingPaymentIntent.value = null
        return true
      }
      return false

    } catch (err) {
      if (isCheckoutAuthError(err)) {
        requireCheckoutAuth()
        return false
      }
      // 同样是用户主动发起的这次支付动作失败后的核对——真支付成功就该看到
      // 完整成功页，而不是静默对账、让用户以为支付真的失败了。P0-B2b P0
      // fix：这里绝不能用会重新读 pendingOrderId.value 的
      // recoverPendingPaymentResult()——requestPayment reject 之前，并发的
      // onShow/后台恢复完全可能已经确认了这笔订单已支付并清空了
      // pendingOrderId，届时公开函数会直接因为"没有 pending 订单"而短路
      // 返回 false，白白把一次真实支付成功误判成失败。必须用一开始就冻结好
      // 的 paymentOrderId 去核对服务端 truth——客户端 requestPayment 的
      // reject 从来就不是支付事实本身。
      if (await recoverPaymentResultById(paymentOrderId, { showDetail: true, presentSuccess: true })) return true
      const msg = err?.errMsg || err?.message || '支付失败，请重试'
      paymentFailed.value = true
      if (String(msg).includes('cancel')) {
        uni.showToast({ title: toastText.payCancelled, icon: 'none' })
      } else {
        uni.showToast({ title: String(msg).slice(0, 30), icon: 'none' })
      }
      return false
    } finally {
      paying.value = false
    }
  }

  return {
    createPaymentIntent,
    goCheckout,
    cancelCheckoutAuth,
    cancelMemberCheckoutChoice,
    checkoutAsGuest,
    joinMemberAndCheckout,
    continuePendingPaymentIntent,
    handleCheckoutAuth,
    performSubmitOrder,
    submitOrder,
    confirmPay,
    savePendingPaymentOrder,
    restorePendingPaymentOrder,
    clearPendingPaymentOrder,
    clearStalePrepayOrderForPayLater,
    recoverPendingPaymentResult,
    // 只为测试可见——生产代码路径一律走 recoverPendingPaymentResult 或者
    // confirmPay 自己冻结好的 paymentOrderId，不直接调用它。
    recoverPaymentResultById,
    requireCheckoutAuth,
  }
}
