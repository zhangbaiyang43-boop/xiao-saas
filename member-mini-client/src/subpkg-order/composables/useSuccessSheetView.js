import { computed } from 'vue'
import { successText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的支付成功面板（PaymentSuccessSheet）文案展示逻辑——都是
// 只读派生计算，不改任何页面状态。逻辑跟原来在 menu.vue 里的一字未改，只是
// 搬了个位置。
export function useSuccessSheetView({ successItems, orderNo, orderId, orderStatus, successPaymentMode }) {
  const successOrderItemCount = computed(() =>
    successItems.value.reduce((sum, item) => sum + Number(item.qty || 0), 0)
  )
  // postpay/table_account 提交成功时没有实际收款（need_payment=false，从没调
  // 起过微信支付），成功页不能沿用 prepay 那句"实付金额"，否则是在断言一笔
  // 没发生过的收款。哪个模式用哪句文案，跟这笔订单自己的 payment_mode 绑定
  // （useCheckout.js 的 hydratePaidSuccessPresentation 里赋值），不是页面当前
  // 状态，避免跟另一笔订单的模式串了。
  const successPaidLabel = computed(() =>
    successPaymentMode?.value === 'prepay' ? successText.paidLabel : successText.payableLabel
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
    successPaidLabel,
    successOrderNo,
    successStatusText,
    successStatusTone,
    orderStatusText,
    orderStatusClass,
  }
}
