// Phase F1E-B — 商家套餐 UI 的纯业务逻辑，从组件里拆出来是为了能被
// scripts/test-subscription-*.mjs 直接 import 做真实断言，而不是只能
// 对 .vue 源码做字符串存在性检查。价格/状态文案/套餐选择器状态/在线支付
// 就绪判定 全部收在这里，SubscriptionSettings.vue / Dashboard.vue 只消费。

export const PLAN_CODE_FREE = 'FREE'
export const PLAN_CODE_STANDARD = 'STANDARD'
export const PLAN_CODE_PRO = 'PRO'

const PLAN_DISPLAY_NAME = { FREE: '免费版', STANDARD: '普通版', PRO: '专业版' }

export function planDisplayName(planCode) {
  return PLAN_DISPLAY_NAME[planCode] || planCode || ''
}

// 金额权威只在 Backend（GET /subscription/plans 的 price_month_cents /
// price_year_cents）——这里只负责 cents -> ¥ 的展示格式化，不参与定价。
// 整数元不展示小数（¥59），非整数才展示两位小数（¥123.45），两种情况都
// 直接来自传入的 cents，从不在前端做 ×12×折扣 之类的推导。
export function formatYuan(cents) {
  const yuan = (Number(cents) || 0) / 100
  return Number.isInteger(yuan) ? `¥${yuan}` : `¥${yuan.toFixed(2)}`
}

export function formatPlanPrice(cents, billingPeriod) {
  const suffix = billingPeriod === 'YEAR' ? '/年' : '/月'
  return `${formatYuan(cents)}${suffix}`
}

// 年付优惠展示：14% 这个数字来自 Backend API 的 annual_discount_display
// 字段（营销展示值，不是运行时计算），FREE 套餐该字段为 null，不展示。
export function annualDiscountCopy(plan) {
  if (!plan || !plan.annual_discount_display) return ''
  return `年付省约${plan.annual_discount_display}`
}

export function formatDate(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 当前套餐状态卡（Phase F1E-B §8）：商家只看得到商家语言，TRIAL/ACTIVE/
// EXPIRED/CANCELLED 这些数据库状态词绝不直接展示。
export function currentPlanCardCopy(sub) {
  const status = sub?.subscription_status
  if (status === 'TRIAL') {
    return {
      title: '专业版试用中',
      subtitle: `剩余 ${sub.days_remaining ?? 0} 天`,
      detail: sub.trial_ends_at ? `试用截止 ${formatDate(sub.trial_ends_at)}` : '',
      ctaText: '',
    }
  }
  if (status === 'ACTIVE') {
    return {
      title: planDisplayName(sub.effective_plan_code),
      subtitle: sub.paid_ends_at ? `有效期至 ${formatDate(sub.paid_ends_at)}` : '',
      detail: '',
      ctaText: '',
    }
  }
  if (status === 'EXPIRED' || status === 'CANCELLED') {
    return { title: '套餐已到期，当前使用免费版', subtitle: '', detail: '', ctaText: '重新开通' }
  }
  // FREE 或未知/加载中状态一律按 FREE 展示，不猜测。
  return { title: '免费版', subtitle: '', detail: '', ctaText: '' }
}

// 首页低视觉强度状态条（Phase F1E-B §3）。只需要 GET /subscription/current
// 一次读取即可推导，不需要 plans/readiness。
export function homeStatusStripCopy(sub) {
  if (!sub) return null
  const status = sub.subscription_status
  if (status === 'TRIAL') {
    return { text: `专业版试用中 · 剩余${sub.days_remaining ?? 0}天`, cta: '查看', urgent: false }
  }
  if (status === 'ACTIVE') {
    const name = planDisplayName(sub.effective_plan_code)
    const dateText = sub.paid_ends_at ? formatDate(sub.paid_ends_at) : ''
    const nearExpiry = typeof sub.days_remaining === 'number' && sub.days_remaining <= 14
    return {
      text: `${name}${dateText ? ' · ' + dateText + '到期' : ''}`,
      cta: nearExpiry ? '续费' : '查看',
      urgent: nearExpiry,
    }
  }
  if (status === 'EXPIRED' || status === 'CANCELLED') {
    return { text: '套餐已到期，当前使用免费版', cta: '重新开通', urgent: true }
  }
  return { text: '免费版', cta: '升级', urgent: false }
}

// 套餐选择器卡片状态（Phase F1E-B §13）。FREE 卡片永远只展示，没有购买 CTA
// ——买 FREE 这件事在冻结合同里根本不存在。STANDARD/PRO 按当前状态决定
// enabled/disabled 与文案，跨档在 ACTIVE 未到期期间必须被挡在点击之前，
// 而不是让商家点了才收到 409。
export function planCardState(sub, planCode) {
  if (planCode === PLAN_CODE_FREE) {
    const isCurrent = !sub || ['FREE', 'EXPIRED', 'CANCELLED'].includes(sub.subscription_status)
    return { kind: 'free', enabled: false, isCurrent, ctaText: '', disabledReason: '' }
  }

  const status = sub?.subscription_status
  const effective = sub?.effective_plan_code

  if (status === 'ACTIVE') {
    if (effective === planCode) {
      return { kind: 'current-paid', enabled: true, isCurrent: true, ctaText: `续费${planDisplayName(planCode)}`, disabledReason: '' }
    }
    return { kind: 'blocked-cross-plan', enabled: false, isCurrent: false, ctaText: '', disabledReason: '当前套餐到期后可切换' }
  }

  if (status === 'TRIAL') {
    return { kind: 'trial-purchase', enabled: true, isCurrent: false, ctaText: `购买${planDisplayName(planCode)}`, disabledReason: '' }
  }

  // FREE / EXPIRED / CANCELLED / 无 Subscription：没有需要保护的有效付费权益。
  return { kind: 'open-purchase', enabled: true, isCurrent: false, ctaText: `开通${planDisplayName(planCode)}`, disabledReason: '' }
}

// Trial 购买披露（Phase F1E-B §16）。Trial 永远是 PRO（冻结合同），所以
// "专业版权益将立即结束" 只在选择了非当前 Trial 套餐（即 STANDARD）时追加。
export function trialDisclosure(sub, selectedPlanCode) {
  if (sub?.subscription_status !== 'TRIAL') return ''
  const base = '购买后将立即切换至所选套餐，剩余试用天数会自动计入套餐有效期。'
  if (selectedPlanCode && selectedPlanCode !== sub.effective_plan_code) {
    return `${base} 专业版权益将立即结束。`
  }
  return base
}

// 商家可读的购买失败文案（Phase F1E-B §22）。Backend 目前把错误原因放在
// error_response 的 msg 文本里（没有单独的机器可读 code 字段），所以这里
// 用固定子串匹配 F1D/F1E-A 已知的原始异常消息，而不是猜测/展示原始英文。
const ERROR_MESSAGE_MAP = [
  [/plan not found/i, '该套餐暂不可用，请刷新后重试'],
  [/plan inactive/i, '该套餐已下架，请选择其它套餐'],
  [/invalid billing_period/i, '请选择月付或年付'],
  [/active paid subscription for a/i, '当前套餐生效中，到期后才能切换其它套餐'],
  [/REAL PAYMENT BLOCKED/i, '在线支付暂未开放，请稍后再试'],
]

export function mapPurchaseErrorMessage(rawMessage) {
  const text = String(rawMessage || '')
  for (const [pattern, copy] of ERROR_MESSAGE_MAP) {
    if (pattern.test(text)) return copy
  }
  return '续费失败，请稍后重试'
}

// 续费下单请求体（Phase F1E-B §19）：只能表达 plan_code + billing_period，
// 永远不包含 amount/amount_cents/tenant_id/discount ——哪怕以后不小心在
// 调用处多传了字段，这个函数本身的返回值形状就是唯一 authority。
export function buildRenewalOrderPayload(planCode, billingPeriod) {
  return { plan_code: planCode, billing_period: billingPeriod }
}

// 在线支付就绪判定（Phase F1E-B §17/§18）：只有当 readiness 请求真正成功
// 且明确返回 true 时才判定为可用；请求失败、返回异常、字段缺失都必须
// fail closed 为不可用——不得因为拿不到答案就默认放行。
export function resolveOnlinePaymentAvailable(readinessResult) {
  if (!readinessResult || readinessResult.ok !== true) return false
  return readinessResult.data?.online_payment_available === true
}

// 账单支付状态轮询的终态判断（Phase F1E-B §20）。
export function isBillingPaymentTerminal(status) {
  return ['PAID', 'FAILED', 'CANCELLED', 'REFUNDED'].includes(status)
}

export function isBillingPaymentWaiting(status) {
  return status === 'PENDING'
}
