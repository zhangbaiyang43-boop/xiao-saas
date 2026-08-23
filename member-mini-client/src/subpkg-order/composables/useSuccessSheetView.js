import { computed } from 'vue'
import { successText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的支付成功面板（PaymentSuccessSheet）文案展示逻辑——都是
// 只读派生计算，不改任何页面状态。逻辑跟原来在 menu.vue 里的一字未改，只是
// 搬了个位置。
export function useSuccessSheetView({ successItems, orderNo, orderId, orderStatus }) {
  const successOrderItemCount = computed(() =>
    successItems.value.reduce((sum, item) => sum + Number(item.qty || 0), 0)
  )
  const successOrderNo = computed(() => orderNo.value || (orderId.value ? String(orderId.value).slice(-4) : '--'))
  const successStatusText = computed(() => ({
    pending_payment: successText.statusPendingPayment,
    pending: successText.statusPending,
    paid: successText.statusPending,
    accepted: successText.statusPreparing,
    preparing: successText.statusPreparing,
    done: successText.statusDone,
    completed: successText.statusDone,
    settled: successText.statusDone,
    rejected: successText.statusRejected,
    cancelled: successText.statusRejected,
  })[orderStatus.value] || successText.statusFallback)
  const successStatusTone = computed(() => {
    if (['preparing', 'accepted'].includes(orderStatus.value)) return 'preparing'
    if (['done', 'completed', 'settled'].includes(orderStatus.value)) return 'done'
    if (['rejected', 'cancelled'].includes(orderStatus.value)) return 'warning'
    return 'pending'
  })
  const orderStatusText = successStatusText
  const orderStatusClass = computed(() => orderStatus.value)

  return {
    successOrderItemCount,
    successOrderNo,
    successStatusText,
    successStatusTone,
    orderStatusText,
    orderStatusClass,
  }
}
