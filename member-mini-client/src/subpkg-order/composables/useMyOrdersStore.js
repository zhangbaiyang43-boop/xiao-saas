import { cancelOrder } from '@/api/order'

// 从 menu.vue 拆出来的"本地订单列表"持久化 + 取消订单。myOrders 是本设备/本桌
// 在这个店見过的订单列表，存本地（不是从后端整体拉取的权威列表，权威列表靠
// syncDiningOrders 之类的高风险流程去同步）——这里只管存/取/取消这三个动作。
//
// 之所以标为 MEDIUM 而不是 LOW：doCancelOrder 会真的调一次取消订单的后端
// 接口，是会改动订单真实状态的操作，不是纯本地展示逻辑；虽然只影响顾客自己
// 这一单（不是支付/结账/桌台结算那条高风险链路），仍然要小心验证。
//
// stopStatusPoll 用回调而不是直接传函数引用，是因为它在 menu.vue 里声明的
// 位置比这个组合式函数的调用位置靠后——回调体要等真正取消成功那一刻才会执行，
// 那时候 stopStatusPoll 早就声明好了，跟 useMemberCard 里 onGoOrder 的道理
// 一样。
export function useMyOrdersStore({ myOrders, shopId, tableNo, orderId, orderStatus, showSuccess, diningParticipantToken, stopStatusPoll }) {
  const storageKey = () => 'my_orders_' + shopId.value + '_' + tableNo.value

  function saveMyOrders() {
    try { uni.setStorageSync(storageKey(), JSON.stringify(myOrders.value)) } catch (e) {}
  }

  function loadMyOrders() {
    try {
      const raw = uni.getStorageSync(storageKey())
      if (raw) myOrders.value = JSON.parse(raw)
    } catch (e) {}
  }

  const doCancelOrder = (order) => {
    uni.showModal({
      title: '取消订单',
      content: '确认取消此订单吗？商家接单后无法取消。',
      success: async ({ confirm }) => {
        if (!confirm) return
        try {
          await cancelOrder(order.id, diningParticipantToken.value || uni.getStorageSync('dining_participant_token'))
          order.status = 'cancelled'
          saveMyOrders()
          if (orderId.value === order.id) {
            stopStatusPoll()
            orderStatus.value = 'cancelled'
            showSuccess.value = false
          }
          uni.showToast({ title: '订单已取消', icon: 'success', duration: 1200 })
        } catch {
          uni.showToast({ title: '取消失败，请重试', icon: 'none', duration: 1200 })
        }
      }
    })
  }

  return {
    saveMyOrders,
    loadMyOrders,
    doCancelOrder,
  }
}
