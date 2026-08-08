import { ref } from 'vue'
import { getCurrentDiningOrders } from '@/api/order'
import { bindDiningParticipant } from '@/api/auth'
import { resolveDiningIdentity, persistDiningContext as persistDiningStorage, isDiningIdentityError } from '@/utils/dining'
import { orderModeText, toastText, modalText } from '../utils/orderText.js'
import { reportError } from '@/utils/monitor'

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
}) {
  // 只更新本组件的响应式状态；实际的"怎么建立/校验本桌身份、往 storage 写哪些字段"
  // 全部收敛到 utils/dining.js 的 resolveDiningIdentity/persistDiningContext，跟扫码
  // 入口页（entry/index.vue）共用同一份实现，不再各自维护一份。
  const persistDiningContext = (data = {}) => {
    diningSessionId.value = data.dining_session_id || diningSessionId.value || ''
    diningParticipantToken.value = data.participant_token || diningParticipantToken.value || ''
    diningClientId.value = data.client_id || diningClientId.value || ''
    persistDiningStorage(data)
  }

  const ensureDiningSession = async (force = false) => {
    const tenantId = shopId.value || uni.getStorageSync('tenant_id') || ''
    const table = tableNo.value || uni.getStorageSync('table_no') || ''
    if (tableSessionClosed.value && !force) return false
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
    const created = order.created_at ? new Date(order.created_at) : new Date()
    const timeStr = Number.isNaN(created.getTime()) ? '' : created.getHours().toString().padStart(2,'0') + ':' + created.getMinutes().toString().padStart(2,'0')
    return {
      id: String(order.id || ''),
      orderNo: String(order.order_no || order.id || '').slice(-4),
      status: order.status || 'pending',
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
      tableSessionClosed.value = res.data?.closed === true || ['CLOSED', 'EXPIRED'].includes(sessionStatus)
      if (tableSessionClosed.value) {
        tableSessionClosedNotice.value = '本桌用餐已结束，如需继续点餐，请重新扫码进入新一桌'
        // Session closed: clear the local "which table" markers so the
        // mine page won't keep showing this settled table as still dining.
        uni.removeStorageSync('table_no')
        uni.removeStorageSync('table_no_at')
        uni.removeStorageSync('dining_session_id')
        uni.removeStorageSync('dining_participant_id')
        uni.removeStorageSync('dining_participant_token')
        uni.removeStorageSync('dining_table_no')
      }
      checkoutRequestedAt.value = res.data?.checkout_requested_at || ''
      tableSessionClosedAt.value = res.data?.closed_at || ''
      myOrders.value = (res.data?.orders || []).map(mapServerOrder)
      saveMyOrders()

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
  }
}
