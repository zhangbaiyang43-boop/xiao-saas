/**
 * 商家后台桌牌 UI 纯展示辅助。
 * 发牌资格只消费后端 order.can_assign_pickup_no，禁止前端再推导 payment_mode / paid。
 */

export function needsPickup(order) {
  const can = order?.canAssignPickupNo ?? order?.can_assign_pickup_no
  return !!can && !order.pickup_no
}

/** 已有号时的次级「更换」：不猜支付模式，仅排除终态 */
export function canReplacePickup(order) {
  if (!order?.pickup_no) return false
  const status = order.status || ''
  return !['cancelled', 'rejected', 'settled'].includes(status)
}

export function pickupConflictToast(pickupNo) {
  const n = String(pickupNo || '').trim()
  return n ? `${n}号刚被使用，请拿其他桌牌` : '该桌牌刚被使用，请拿其他桌牌'
}
