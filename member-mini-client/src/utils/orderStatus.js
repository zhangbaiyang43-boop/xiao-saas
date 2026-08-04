// 订单状态 -> 展示态的映射，供悬浮气泡等跨页面复用的小组件使用。
// menu.vue 内部已经有自己的一套同名 computed（历史实现，覆盖更多状态如 timeline/title），
// 那套不做改动以避免影响既有堂食流程；这里是给新的、跨页面场景（订单气泡）用的精简版，
// 保持和 menu.vue 里的文案完全一致，避免两处措辞对不上。
const STATUS_ALIASES = {
  paid: 'pending',
  pending: 'pending',
  accepted: 'preparing',
  preparing: 'preparing',
  cooking: 'preparing',
  done: 'done',
  completed: 'done',
  settled: 'settled',
  cancelled: 'cancelled',
  rejected: 'rejected',
}

export const normalizeOrderStatus = (status) => STATUS_ALIASES[status] || 'pending'

const TONE_BY_STATUS = {
  pending: 'paid',
  preparing: 'preparing',
  done: 'served',
  settled: 'settled',
  cancelled: 'canceled',
  rejected: 'canceled',
}

export const orderStatusTone = (status) => TONE_BY_STATUS[normalizeOrderStatus(status)] || 'paid'

const ICON_BY_TONE = {
  canceled: 'icon-warnfill',
  paid: 'icon-pay',
  preparing: 'icon-beican',
  served: 'icon-deliver',
  settled: 'icon-roundcheckfill',
}

export const orderStatusIcon = (tone) => ICON_BY_TONE[tone] || 'icon-pay'

const BADGE_BY_TONE = {
  canceled: '异常状态',
  paid: '正常进行',
  preparing: '正在备餐',
  served: '已送达',
  settled: '订单完成',
}

export const orderStatusBadge = (tone) => BADGE_BY_TONE[tone] || '正常进行'

const NEXT_ACTION_BY_TONE = {
  canceled: '重新点餐',
  paid: '无需操作，请稍候',
  preparing: '等待上餐即可',
  served: '请确认菜品',
  settled: '可关闭查看',
}

export const orderStatusNextAction = (tone) => NEXT_ACTION_BY_TONE[tone] || '无需操作，请稍候'
