import { createOrder, createWxPayOrder, getOrderStatus } from '@/api/order'
import { joinByEntranceCode } from '@/api/auth'
import { saveCustomerSession, clearCustomerSession } from '@/utils/auth'
import { isDiningIdentityError } from '@/utils/dining'
import { reportError } from '@/utils/monitor'
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
// refreshCustomerAuthState/saveMyOrders/startStatusPoll/consumeWelcomeCoupon
// 这些来自别的组合式函数的方法，都是回调传入，不在这里重新实现。
export function useCheckout({
  shopId, tableNo, diningSessionId, diningParticipantToken, diningClientId,
  orderNo, orderId, orderStatus, successItems, successTotal, successDiscount,
  showCheckoutAuth, authorizing, authActionStatus, pendingPaymentIntent, paying, paymentFailed,
  payAmount, pendingOrderId, pendingSubmitRequestId,
  myOrders, showOrders, showCart, showSuccess,
  ordering, tableSessionClosed, paymentMode,
  reminderRequested, earnedCoupon, cart, specCartItems, remark, selectedCouponId,
  totalPrice, cartItems, finalPrice, wechatPayAmount, isPrepayMode, canSubmitOrder,
  orderSuccessTemplateId, pickupReminderTemplateId,
  wxLogin, ensureDiningSession, bindCurrentDiningParticipant, syncDiningOrders,
  normalizePaymentMode, refreshCustomerAuthState, saveMyOrders, startStatusPoll, consumeWelcomeCoupon,
}) {
  const ensureSubmitRequestId = () => {
    if (!pendingSubmitRequestId.value) {
      pendingSubmitRequestId.value = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    }
    return pendingSubmitRequestId.value
  }

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

  const pendingPaymentStorageKey = () => 'pending_payment_order_' + shopId.value + '_' + tableNo.value

  const savePendingPaymentOrder = () => {
    if (!pendingOrderId.value) return
    try {
      uni.setStorageSync(pendingPaymentStorageKey(), JSON.stringify({
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
    try {
      const raw = uni.getStorageSync(pendingPaymentStorageKey())
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
    try { uni.removeStorageSync(pendingPaymentStorageKey()) } catch (e) {}
    pendingOrderId.value = ''
    paymentFailed.value = false
  }

  const clearStalePrepayOrderForPayLater = () => {
    if (isPrepayMode.value || !pendingOrderId.value) return
    clearPendingPaymentOrder()
    pendingPaymentIntent.value = null
  }

  const isPaidOrSubmittedOrder = (order) => {
    const status = order?.status || ''
    const paymentStatus = order?.payment_status || ''
    return paymentStatus === 'paid' || ['pending', 'paid', 'accepted', 'preparing', 'done', 'completed', 'settled'].includes(status)
  }

  let recoveringPayment = false
  const recoverPendingPaymentResult = async ({ showDetail = false } = {}) => {
    if (recoveringPayment) return false
    restorePendingPaymentOrder()
    const id = pendingOrderId.value
    if (!id) return false
    recoveringPayment = true
    try {
      const res = await getOrderStatus(id, diningParticipantToken.value)
      const data = res?.data || {}
      if (isPaidOrSubmittedOrder(data)) {
        orderId.value = id
        orderStatus.value = data.status || 'pending'
        showCart.value = false
        showCheckoutAuth.value = false
        pendingPaymentIntent.value = null
        clearPendingPaymentOrder()

        const now = new Date()
        const existed = myOrders.value.find(o => String(o.id) === String(id))
        if (existed) {
          existed.status = orderStatus.value
        } else {
          myOrders.value.unshift({
            id,
            orderNo: orderNo.value || String(id).slice(-4),
            status: orderStatus.value,
            items: successItems.value,
            total: successTotal.value || payAmount.value,
            createdAt: now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0'),
            createdTs: now.getTime(),
            table: tableNo.value,
          })
        }
        saveMyOrders()
        startStatusPoll(id)
        await syncDiningOrders()
        showOrders.value = showDetail || showOrders.value
        return true
      }
      if (['cancelled', 'rejected'].includes(data.status)) {
        clearPendingPaymentOrder()
      }
      return false
    } catch (e) {
      // 底层网络失败本身已经在 api/request.js 里报过一次了，这里单独再报一次
      // 是因为"对账失败"这件事本身有独立的排查价值——能单独统计"待支付订单
      // 恢复失败率"，不用从一堆通用网络错误里去猜。
      reportError('checkout.recover_pending_payment', e)
      return false
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

  const goCheckout = () => {
    if (ordering.value || paying.value || authorizing.value) return
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
    submitOrder()
  }

  const cancelCheckoutAuth = () => {
    if (authorizing.value) return
    showCheckoutAuth.value = false
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
    try {
      const sessionReady = await ensureDiningSession()
      if (!sessionReady || tableSessionClosed.value) {
        throw new Error(tableSessionClosed.value ? toastText.tableSessionEnded : toastText.tableSessionUnavailable)
      }
      // 必须在用户点击提交的手势链里调用，否则微信不会弹授权框。
      await requestOrderSubscribeMessages()
      const payload = {
        table: tableNo.value,
        shop: shopId.value,
        total: totalPrice.value,
        remark: remark.value.trim() || undefined,
        coupon_id: selectedCouponId.value || undefined,
        dining_session_id: diningSessionId.value || undefined,
        participant_token: diningParticipantToken.value || undefined,
        client_id: diningClientId.value || undefined,
        request_id: ensureSubmitRequestId(),
        items: cartItems.value.map((item) => ({ dish_id: item.id, name: item.orderName || item.name, price: item.price, qty: item.qty, specifications: item.specifications && item.specifications.length ? item.specifications : undefined, extras: item.extras && item.extras.length ? item.extras : undefined })),
      }
      const res = await createOrder(payload, { authRedirect: false })
      const data = res?.data || {}
      pendingOrderId.value = String(data.id || data.order_id || '')
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
      _handlePaySuccess({ ...data, total: payAmount.value, status: data.status || 'pending' })
      pendingPaymentIntent.value = null
      return true
    } catch (err) {
      // 本桌匿名身份失效（后端统一返回 409）不是会员登录问题，静默重建身份后自动重试
      // 一次；仍失败才走下面的兜底提示，不会弹"继续支付/授权"这种会员专属的措辞。
      if (!isRetry && isDiningIdentityError(err)) {
        const rebuilt = await ensureDiningSession(true)
        if (rebuilt) return performSubmitOrder(true)
      }
      if (isCheckoutAuthError(err)) {
        requireCheckoutAuth()
        return false
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
      const msg = isDiningIdentityError(err)
        ? (rawMsg || toastText.tableSessionUnavailable)
        : (rawMsg || toastText.submitOrderFailed)
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

  const _handlePaySuccess = (data) => {
    showCart.value = false
    orderId.value = pendingOrderId.value
    orderStatus.value = data.status || 'pending'
    successTotal.value = Number(data.total ?? payAmount.value)
    startStatusPoll(orderId.value)
    const now = new Date()
    const timeStr = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0')
    myOrders.value.unshift({
      id: orderId.value, orderNo: orderNo.value, status: orderStatus.value,
      paymentStatus: data.payment_status || '', paymentMode: normalizePaymentMode(data.payment_mode || paymentMode.value),
      diningSessionId: diningSessionId.value || '', tableSessionId: diningSessionId.value || '',
      items: successItems.value, total: successTotal.value, createdAt: timeStr,
      createdTs: now.getTime(), table: tableNo.value,
      pickupNo: data.pickup_no || '',
    })
    saveMyOrders()
    syncDiningOrders().catch(() => {})
    reminderRequested.value = false
    applyRewardCoupon(data.coupon || null)
    cart.value = {}
    specCartItems.value = []
    selectedCouponId.value = null
    remark.value = ''
    pendingSubmitRequestId.value = ''
    showSuccess.value = true
    clearPendingPaymentOrder()
  }

  // 把"后端返回的奖励券"拓成 earnedCoupon 的展示形状：有真实奖励券就用它，
  // 没有（c 为 null）则回退到本地缓存的入会欢迎券，免得支付完成那一刻什么都不展示。
  const applyRewardCoupon = (c) => {
    if (c) {
      earnedCoupon.value = {
        couponId: c.id || '',
        amount: Number(c.value ?? c.amount ?? 0),
        threshold: Number(c.min_amount ?? c.threshold ?? 0),
        // 后端给的是绝对过期时间 expired_at，不是相对天数，
        // 直接存成 expire_time 方便复用下面的 couponValidityText。
        expire_time: c.expired_at || '',
        name: c.name || '优惠券',
        isSecondOrder: Boolean(c.is_second_order),
      }
      return true
    }
    const welcome = consumeWelcomeCoupon()
    earnedCoupon.value = welcome ? {
      couponId: welcome.id || '',
      amount: Number(welcome.amount ?? welcome.value ?? 0),
      threshold: Number(welcome.min_amount ?? welcome.threshold ?? 0),
      expire_time: welcome.expired_at || '',
      name: welcome.name || '新人优惠券',
    } : null
    return false
  }

  // 真实微信支付的奖励券是异步发的（wxpay_notify 回调落库），客户端 requestPayment
  // 刚成功那一刻后端未必已经处理完，所以先用回退文案展示，再在后台短轮询 /orders/my
  // 拿到真实发放的奖励券后补上去——若用户已关闭成功面板或已去看其他订单就不再改。
  const attachPaymentReward = async (id) => {
    for (let attempt = 0; attempt < 6; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 900))
      try {
        const res = await getOrderStatus(id, diningParticipantToken.value)
        const d = res?.data || {}
        if (d.payment_status === 'paid') {
          if (showSuccess.value && orderId.value === id && d.reward_coupon) {
            applyRewardCoupon(d.reward_coupon)
          }
          return
        }
      } catch (e) { /* keep retrying */ }
    }
  }

  const confirmPay = async () => {
    if (paying.value || !pendingOrderId.value) return false
    paying.value = true
    paymentFailed.value = false
    try {
      // 待支付恢复等只走 confirmPay 的路径，也要再申请一次（已授权时微信通常不再弹框）。
      await requestOrderSubscribeMessages()
      if (await recoverPendingPaymentResult()) return true
      if (showCheckoutAuth.value) authActionStatus.value = 'paying'
      let jsCode = ''
      if (!uni.getStorageSync('customer_token')) {
        jsCode = await wxLogin()
      }
      const res = await createWxPayOrder(pendingOrderId.value, false, { authRedirect: false, js_code: jsCode, participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') })
      const data = res?.data || {}

      if (data.free) {
        _handlePaySuccess(data)
        pendingPaymentIntent.value = null
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

      const paidOrderId = pendingOrderId.value
      _handlePaySuccess({ ...data, total: payAmount.value })
      pendingPaymentIntent.value = null
      // _handlePaySuccess 内部会清空 pendingOrderId，这里用支付前存下的 id 去轮询。
      attachPaymentReward(paidOrderId)
      return true

    } catch (err) {
      if (isCheckoutAuthError(err)) {
        requireCheckoutAuth()
        return false
      }
      if (await recoverPendingPaymentResult({ showDetail: true })) return true
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
    continuePendingPaymentIntent,
    handleCheckoutAuth,
    performSubmitOrder,
    submitOrder,
    applyRewardCoupon,
    attachPaymentReward,
    confirmPay,
    savePendingPaymentOrder,
    restorePendingPaymentOrder,
    clearPendingPaymentOrder,
    clearStalePrepayOrderForPayLater,
    recoverPendingPaymentResult,
    requireCheckoutAuth,
  }
}
