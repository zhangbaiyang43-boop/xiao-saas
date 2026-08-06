import { requestTableCheckout } from '@/api/order'
import { isDiningIdentityError } from '@/utils/dining'
import { reportError } from '@/utils/monitor'

// 从 menu.vue 拆出来的桌台账单结账流程——顾客点"去结账"通知服务员、
// "撤销呼叫"（继续加菜时）、"本桌已结账"的拦截提示。这是 HIGH 风险层里相对
// 自成一体的一块：只依赖 ensureDiningSession/persistDiningContext 两个回调，
// 不像下单/支付那组函数互相递归调用，所以先拆这个练手 409 重试这个模式，
// 再去动风险更高的下单/支付。
//
// performTableCheckout 的 409 重试模式（identity 不同步时先补一次
// ensureDiningSession 再重试一次，isRetry 防止死循环）跟下单那边
// performSubmitOrder 是一模一样的道理——同一类问题（participant_token 跟
// session 状态不同步）在两条不同的后端接口上都会发生，各自独立处理，没有
// 抽成共用函数是因为除了这个重试外两边其余逻辑完全不同，硬抽象只会增加
// 阅读成本。
export function useTableCheckout({
  shopId, diningParticipantToken, diningClientId, tableSessionId,
  canContinueOrder, checkoutRequestedAt, checkoutRequested, isTableSettled, tableCheckouting,
  showOrders, showSuccess, activeTab,
  ensureDiningSession, persistDiningContext,
}) {
  const clearCheckoutRequest = () => {
    if (!checkoutRequestedAt.value) return
    checkoutRequestedAt.value = ''
    requestTableCheckout({
      tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
      dining_session_id: tableSessionId.value,
      participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') || '',
      requested: false,
    }).catch(() => {})
  }

  const handleTableContinueOrder = async () => {
    if (!canContinueOrder.value) {
      uni.showToast({ title: '本桌账单已结束，不能继续加菜', icon: 'none' })
      return
    }
    if (!tableSessionId.value) {
      const ok = await ensureDiningSession(true)
      if (!ok) {
        uni.showToast({ title: '本桌点餐会话不可用，请重新扫码', icon: 'none' })
        return
      }
    }
    // 顾客决定继续加菜，说明这一桌暂时不结账了，之前呼叫服务员的请求就该撤销，
    // 不然等新点的菜也做完了，界面会立刻显示"已呼叫服务员"这种其实早就过期的状态。
    clearCheckoutRequest()
    persistDiningContext({
      dining_session_id: tableSessionId.value,
      participant_token: diningParticipantToken.value,
      client_id: diningClientId.value,
    })
    showOrders.value = false
    showSuccess.value = false
    activeTab.value = 'order'
  }

  const performTableCheckout = async (isRetry = false) => {
    try {
      // participant_token 有时会跟 session 状态不同步（比如缓存只留下了 session_id），
      // 后端校验不到身份会直接 409，先补一次 ensureDiningSession 把它修复回来，
      // 避免明明这一桌点单正常、结账却因为身份缺失而失败。
      if (!diningParticipantToken.value && !uni.getStorageSync('dining_participant_token')) {
        await ensureDiningSession()
      }
      const res = await requestTableCheckout({
        tenant_id: shopId.value || uni.getStorageSync('tenant_id') || '',
        dining_session_id: tableSessionId.value,
        participant_token: diningParticipantToken.value || uni.getStorageSync('dining_participant_token') || '',
        requested: true,
      }, { authRedirect: false })
      if (res?.code === 200) {
        checkoutRequestedAt.value = res.data?.checkout_requested_at || new Date().toISOString()
        uni.vibrateShort({ type: 'heavy' })
        uni.showToast({ title: '已通知服务员，请稍候为您结账', icon: 'none', duration: 2000 })
      } else {
        uni.showToast({ title: res?.msg || '呼叫失败，请重试', icon: 'none' })
      }
    } catch (e) {
      if (!isRetry && isDiningIdentityError(e)) {
        const rebuilt = await ensureDiningSession(true)
        if (rebuilt) return performTableCheckout(true)
      }
      // 走到这里说明呼叫结账最终失败了（要么不是身份问题，要么重建身份后重试
      // 还是失败）——单独用这个 scene 报一下，方便统计"呼叫服务员失败率"，
      // 不用从一堆通用网络错误里去猜是不是这个功能出了问题。
      reportError('table_checkout.request_failed', e, { isRetry })
      uni.showToast({ title: '呼叫失败，请重试', icon: 'none' })
    }
  }

  const handleTableCheckout = async () => {
    if (tableCheckouting.value || checkoutRequested.value) return
    if (isTableSettled.value) {
      uni.showModal({
        title: '本桌已结账',
        content: '本次用餐账单已经结清，如需明细请联系服务员。',
        showCancel: false,
        confirmText: '知道了',
      })
      return
    }
    if (!tableSessionId.value) {
      uni.showToast({ title: '缺少桌台账单信息，请重新加载', icon: 'none' })
      return
    }
    tableCheckouting.value = true
    try {
      await performTableCheckout()
    } finally {
      tableCheckouting.value = false
    }
  }

  return {
    clearCheckoutRequest,
    handleTableContinueOrder,
    performTableCheckout,
    handleTableCheckout,
  }
}
