import { ref } from 'vue'
import { getCurrentDiningOrders } from '@/api/order'
import { bindDiningParticipant } from '@/api/auth'
import { resolveDiningIdentity, persistDiningContext as persistDiningStorage, isDiningIdentityError } from '@/utils/dining'
import { orderModeText, toastText, modalText } from '../utils/orderText.js'
import { reportError } from '@/utils/monitor'
import { parseServerTime, formatBeijingClock } from '@/utils/beijingTime'

// 从 menu.vue 拆出来的"拼桌身份"这条链路——建立/校验本桌身份、绑定当前参与者、
// 拉取本桌所有订单并同步进 myOrders。这是全部拆解里最基础的一块：桌台账单、
// 下单提交、支付、结账，全都要读它写出来的 tableSessionClosed/myOrders 等状态，
// 所以最后才拆、拆的时候也最小心——这里的任何一个字段漏传，都会连带影响上面
// 所有依赖它的高风险流程。
//
// 逻辑跟原来在 menu.vue 里一字未改，只是把用到的页面状态改成参数传入。
// resolveDiningIdentity/persistDiningContext(as persistDiningStorage)/
// isDiningIdentityError 三个来自 utils/dining.js 的实现，跟扫码入口页
// （entry/index.vue）共用同一份，不在这里重新实现。
export function useDiningSession({
  shopId, tableNo, diningSessionId, diningParticipantToken, diningClientId,
  tableSessionClosed, tableSessionStatus, tableSessionTotal, tableSessionClosedNotice,
  checkoutRequestedAt, tableSessionClosedAt, myOrders,
  normalizePaymentMode, saveMyOrders,
  // 可选：CLOSED / exit 时停掉桌台相关轮询（由 menu 注入 stopStatusPoll + stopTablePresencePoll）
  stopDiningPolls,
}) {
  // 退出进行中：防止完成按钮连点、poll 回写 CLOSED UI、ensure 静默复活
  const isExitingSession = ref(false)

  // 只更新本组件的响应式状态；实际的"怎么建立/校验本桌身份、往 storage 写哪些字段"
  // 全部收敛到 utils/dining.js 的 resolveDiningIdentity/persistDiningContext，跟扫码
  // 入口页（entry/index.vue）共用同一份实现，不再各自维护一份。
  const persistDiningContext = (data = {}) => {
    diningSessionId.value = data.dining_session_id || diningSessionId.value || ''
    diningParticipantToken.value = data.participant_token || diningParticipantToken.value || ''
    diningClientId.value = data.client_id || diningClientId.value || ''
    persistDiningStorage(data)
  }

  const clearDiningSessionStorage = () => {
    uni.removeStorageSync('table_no')
    uni.removeStorageSync('table_no_at')
    uni.removeStorageSync('dining_session_id')
    uni.removeStorageSync('dining_participant_id')
    uni.removeStorageSync('dining_participant_token')
    uni.removeStorageSync('dining_table_no')
    // dining_client_id 是设备级匿名 id，跨会话复用，不属于"本次 DiningSession"，保留。
  }

  const stopPollsSafe = () => {
    if (typeof stopDiningPolls === 'function') {
      try { stopDiningPolls() } catch { /* ignore */ }
    }
  }

  // CLOSED 后进入「可展示结账结果」态：
  // - 清 storage，避免其它页把已结账桌当成仍在用餐
  // - 清 participantToken，杜绝继续用旧身份打桌台 API
  // - 保留 diningSessionId + tableNo，供 TableBillSheet 过滤/展示本桌结果
  // - 立刻停 poll；不立刻跳页——用户点「完成」再 exitDiningSession
  const markSessionClosed = (notice) => {
    tableSessionClosed.value = true
    tableSessionClosedNotice.value = notice
      || '本桌用餐已结束，如需继续点餐，请重新扫码进入新一桌'
    clearDiningSessionStorage()
    diningParticipantToken.value = ''
    stopPollsSafe()
  }

  // 彻底退出本次桌台会话（内存 + storage + 停 poll）。不负责导航；调用方 reLaunch。
  // 返回 false 表示已在退出中（幂等）。
  const exitDiningSession = () => {
    if (isExitingSession.value) return false
    isExitingSession.value = true
    stopPollsSafe()
    clearDiningSessionStorage()
    diningSessionId.value = ''
    diningParticipantToken.value = ''
    tableNo.value = ''
    tableSessionClosed.value = false
    tableSessionStatus.value = ''
    tableSessionTotal.value = 0
    tableSessionClosedAt.value = ''
    tableSessionClosedNotice.value = ''
    checkoutRequestedAt.value = ''
    return true
  }

  const ensureDiningSession = async (force = false) => {
    // CLOSED / 退出中：禁止用旧 tableNo 静默重建 DiningSession。重新开桌只能走扫码 entry。
    if (tableSessionClosed.value || isExitingSession.value) return false
    const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
    const table = tableNo.value || uni.getStorageSync('table_no') || ''
    const identity = await resolveDiningIdentity({ tenantId, table, force })
    if (!identity.ok) return false
    persistDiningContext(identity.data)
    tableSessionClosed.value = false
    return true
  }

  const bindCurrentDiningParticipant = async () => {
    if (!diningParticipantToken.value) return
    const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
    if (!tenantId) return
    try {
      await bindDiningParticipant({ tenant_id: tenantId, participant_token: diningParticipantToken.value }, { authRedirect: false })
    } catch (e) {
      // 绑不上参与者身份不阻断当前这次操作（原来就是静默跳过），但单独用
      // 这个 scene 报一下，方便跟"这一桌的拼单人数/权限出问题"这类客诉对上号。
      reportError('dining.bind_participant', e)
    }
  }

  const diningOrderQuery = () => ({
    tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
    dining_session_id: diningSessionId.value || uni.getStorageSync('dining_session_id') || '',
    participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') || '',
  })

  const mapServerOrder = (order) => {
    // created_at 是后端的 naive UTC（无 Z），必须走 parseServerTime 补时区再按
    // 北京时间格式化——直接 new Date() 会被当成本地时间，界面上整整差 8 小时
    // （北京 11:13 下的单会显示成 03:13）。详见 utils/beijingTime.js。
    const created = parseServerTime(order.created_at) || new Date()
    const timeStr = formatBeijingClock(created)
    return {
      id: String(order.id || ''),
      orderNo: String(order.order_no || order.id || '').slice(-4),
      status: order.status || 'pending',
      status_text: order.status_text || '',
      paymentStatus: order.payment_status || '',
      paymentMode: normalizePaymentMode(order.payment_mode),
      diningSessionId: order.dining_session_id ? String(order.dining_session_id) : '',
      tableSessionId: order.dining_session_id ? String(order.dining_session_id) : '',
      items: Array.isArray(order.items) ? order.items.map(i => ({ ...i, qty: Number(i.qty || 0), price: Number(i.price || 0) })) : [],
      total: Number(order.total || 0),
      discountAmount: Number(order.discount_amount || 0),
      tableTotal: Number(order.table_total || order.session_total || 0),
      participantNo: order.participant_no ?? null,
      isStaff: order.source === 'staff',
      staffNote: order.staff_note || '',
      pickupNo: order.pickup_no || '',
      createdAt: timeStr,
      createdTs: Number.isNaN(created.getTime()) ? Date.now() : created.getTime(),
      table: order.table_no || tableNo.value,
      shop: shopId.value,
    }
  }

  // 本桌人数变化提示（参照客如云同款体验）：只在人数比上一次同步"变多"时提醒一次，
  // 第一次同步不提醒（不然刚进桌就弹一个"有人加入"很奇怪，那是自己）。人数不落到
  // 具体是谁，跟"参与者编号"标签是同一个"不暴露真实身份"的原则。
  const knownParticipantCount = ref(0)
  const hasSyncedParticipantCount = ref(false)

  // 身份没就绪（守卫拦下）或后端明确回了 identity_mismatch，都不能悄悄返回"查不到订单"了
  // 事——那跟"这一桌真的还没人点单"在界面上长得一模一样，顾客不会知道是身份出了问题。
  // 这两种情况都先强制重建一次身份再重试，isRetry 保证最多重试一次，不会死循环。
  const syncDiningOrders = async (isRetry = false) => {
    if (isExitingSession.value) return false
    // 已 CLOSED：不再拉旧会话，更不能 ensureDiningSession(true) 静默开新桌
    if (tableSessionClosed.value) return false

    const query = diningOrderQuery()
    if (!query.tenant_id || !query.dining_session_id || !query.participant_token) {
      if (isRetry) return false
      return (await ensureDiningSession(true)) ? syncDiningOrders(true) : false
    }
    try {
      const res = await getCurrentDiningOrders(query)
      if (res?.code !== 200) return false
      if (res.data?.identity_mismatch) {
        if (isRetry) return false
        return (await ensureDiningSession(true)) ? syncDiningOrders(true) : false
      }
      const sessionStatus = String(res.data?.session_status || '').toUpperCase()
      tableSessionStatus.value = sessionStatus
      tableSessionTotal.value = Number(res.data?.table_total || res.data?.session_total || 0)
      checkoutRequestedAt.value = res.data?.checkout_requested_at || ''
      tableSessionClosedAt.value = res.data?.closed_at || ''
      myOrders.value = (res.data?.orders || []).map(mapServerOrder)
      saveMyOrders()

      const closed = res.data?.closed === true || ['CLOSED', 'EXPIRED'].includes(sessionStatus)
      if (closed) {
        markSessionClosed('本桌用餐已结束，如需继续点餐，请重新扫码进入新一桌')
        return true
      }

      tableSessionClosed.value = false

      const newParticipantCount = Number(res.data?.participant_count || 0)
      if (newParticipantCount > 0) {
        if (hasSyncedParticipantCount.value && newParticipantCount > knownParticipantCount.value) {
          uni.showToast({ title: toastText.newParticipant, icon: 'none', duration: 2500 })
        }
        knownParticipantCount.value = newParticipantCount
        hasSyncedParticipantCount.value = true
      }
      return true
    } catch (e) {
      if (!isRetry && isDiningIdentityError(e)) {
        return (await ensureDiningSession(true)) ? syncDiningOrders(true) : false
      }
      return false
    }
  }

  const showTableHint = () => {
    uni.showModal({
      title: modalText.tableHintTitle,
      content: modalText.tableHintContent(tableNo.value || orderModeText.unknownTable),
      showCancel: false,
      confirmText: modalText.tableHintConfirm,
    })
  }

  return {
    persistDiningContext,
    ensureDiningSession,
    bindCurrentDiningParticipant,
    syncDiningOrders,
    showTableHint,
    markSessionClosed,
    // P0-10-05: exported so callers with a NARROWER "identity invalid, not
    // necessarily table closed" signal (e.g. useCheckout's unrecovered 409
    // path) can invalidate the stale cache without markSessionClosed's
    // tableSessionClosed=true side effect, which is specifically wrong for a
    // plain identity mismatch (see useCheckout.js's own comment on this).
    clearDiningSessionStorage,
    exitDiningSession,
    isExitingSession,
  }
}
