import { watch } from 'vue'
import { getOrderStatus } from '@/api/order'
import { toastText, modalText } from '../utils/orderText.js'

// 从 menu.vue 拆出来的"订单状态轮询"——顾客下单/支付成功后，每 15 秒问一次
// 后端这单到没到"制作中/已完成"，以及本桌人数轮询（每 25 秒问一次本桌订单，
// 复用 syncDiningOrders，顺带发现"有新伙伴扫码加入"）。还带一个监听
// orderStatus 变化的副作用：状态跳到"制作中"/"已完成"震动+提示，跳到
// "已拒单"震动+弹窗并停止轮询。
//
// 终态列表（settled/cancelled/rejected）在这里出现了两次（startStatusPoll
// 里、refreshAllOrderStatuses 里），必须跟 useTableBillView.js 里
// pendingOrderCount 判断"这单还要不要继续追踪"用的终态列表保持一致——
// 否则会出现"订单气泡认为已经结束不再提醒，轮询却还在转"或反过来的不一致，
// 这是从原来的 menu.vue 里原样保留的行为，没有改动判断逻辑。
export function useOrderStatusPoll({
  orderStatus, diningParticipantToken, myOrders,
  saveMyOrders, syncDiningOrders, normalizeOrderStatus,
  // 可选：CLOSED / 退出中 / 无 active session 时不要启动桌台轮询
  canPollDiningSession,
}) {
  let statusPollTimer = null
  let tablePresencePollTimer = null

  function stopStatusPoll() {
    if (statusPollTimer) { clearInterval(statusPollTimer); statusPollTimer = null }
  }

  function startStatusPoll(id) {
    stopStatusPoll()
    statusPollTimer = setInterval(() => {
      getOrderStatus(id, diningParticipantToken.value).then((body) => {
        if (body.code === 200) {
          const newStatus = body.data?.status || 'pending'
          orderStatus.value = newStatus
          const rec = myOrders.value.find(o => o.id === id)
          if (rec) {
            let dirty = false
            if (rec.status !== newStatus) { rec.status = newStatus; dirty = true }
            const nextPickup = body.data?.pickup_no || ''
            if (nextPickup && rec.pickupNo !== nextPickup) { rec.pickupNo = nextPickup; dirty = true }
            if (dirty) saveMyOrders()
          }
          if (['settled', 'cancelled', 'rejected'].includes(newStatus)) stopStatusPoll()
        }
      }).catch(() => { })
    }, 15000)
  }

  function stopTablePresencePoll() {
    if (tablePresencePollTimer) { clearInterval(tablePresencePollTimer); tablePresencePollTimer = null }
  }

  // 本桌人数轮询：只在顾客真的停留在点餐页时跑，间隔比订单状态轮询（15秒）更松——
  // "有人加入"不是紧急信息，稍微有延迟没关系，没必要跟催单一样频繁。onHide/onUnload
  // 会停掉，不在后台空耗电量和流量。
  function startTablePresencePoll() {
    stopTablePresencePoll()
    if (typeof canPollDiningSession === 'function' && !canPollDiningSession()) return
    tablePresencePollTimer = setInterval(() => {
      if (typeof canPollDiningSession === 'function' && !canPollDiningSession()) {
        stopTablePresencePoll()
        return
      }
      syncDiningOrders().catch(() => {})
    }, 25000)
  }

  async function refreshAllOrderStatuses() {
    if (await syncDiningOrders()) return
    const orders = myOrders.value.filter(o => !['settled', 'cancelled', 'rejected'].includes(normalizeOrderStatus(o.status)))
    orders.forEach(order => {
      getOrderStatus(order.id, diningParticipantToken.value).then((body) => {
        if (body.code === 200) {
          const newStatus = body.data?.status || order.status
          const rec = myOrders.value.find(o => o.id === order.id)
          if (rec) {
            let dirty = false
            if (rec.status !== newStatus) { rec.status = newStatus; dirty = true }
            const nextPickup = body.data?.pickup_no || ''
            if (nextPickup && rec.pickupNo !== nextPickup) { rec.pickupNo = nextPickup; dirty = true }
            if (dirty) saveMyOrders()
          }
        }
      }).catch(() => {})
    })
  }

  watch(orderStatus, (newVal, oldVal) => {
    if (newVal === 'preparing' && oldVal === 'pending') {
      uni.vibrateShort({ type: 'heavy' })
      uni.showToast({ title: toastText.merchantAccepted, icon: 'none', duration: 2500 })
    } else if (newVal === 'done') {
      uni.vibrateShort({ type: 'heavy' })
    } else if (newVal === 'rejected') {
      stopStatusPoll()
      uni.vibrateShort({ type: 'heavy' })
      uni.showModal({
        title: modalText.orderRejectedTitle,
        content: modalText.orderRejectedContent,
        showCancel: false,
      })
    }
  })

  return {
    startStatusPoll,
    stopStatusPoll,
    startTablePresencePoll,
    stopTablePresencePoll,
    refreshAllOrderStatuses,
  }
}
