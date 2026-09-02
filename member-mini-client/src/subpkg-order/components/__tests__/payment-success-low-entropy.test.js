import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../../../')
const read = (rel) => readFileSync(path.join(srcRoot, rel), 'utf8')

// PaymentSuccessSheet 是「下单 / 支付成功」之后的状态确认页——不是订单 Dashboard、
// 不是会员营销页、也不是订单详情页。B 版把首屏收敛成一条交易主线：
//   成功 → 实付 / 本单金额 → 实时订单状态 → [条件] 领桌牌 → 弱会员 / 弱券 → 桌号
//         → 查看本桌订单 / 继续加菜 / 关闭
// 这个 contract 锁的是「哪些信息不允许再爬回成功页首屏」以及「下一步操作层级」，
// 不锁字号 / 颜色 / 间距（视觉可安全微调），也不锁完整中文文案 snapshot。

const FULL = read('subpkg-order/components/PaymentSuccessSheet.vue')
const TEMPLATE = FULL.slice(
  FULL.indexOf('<template>') + '<template>'.length,
  FULL.lastIndexOf('</template>'),
)
const SCRIPT = FULL.slice(
  FULL.indexOf('<script>') + '<script>'.length,
  FULL.indexOf('</script>'),
)
// 券区结构性切片——不用固定字符窗口。`.reward-coupon` <view> 内只有 <template>
// 分支和 <text>，没有嵌套 <view>，所以「class="reward-coupon" 之后第一个 </view>」
// 就是券块自身的收尾，与后面加多少行无关。
const couponRegion = () => {
  const a = TEMPLATE.indexOf('class="reward-coupon"')
  if (a === -1) return ''
  const z = TEMPLATE.indexOf('</view>', a)
  return z === -1 ? '' : TEMPLATE.slice(a, z + '</view>'.length)
}
// S6（pickup 待领取）分支 = `<template v-if="pickupNoEnabled && !pickupNo">` 到
// `<template v-else>` 之间；S5（普通）分支 = `<template v-else>` 到券区结尾。
const s6Region = () => {
  const r = couponRegion()
  const a = r.indexOf('v-if="pickupNoEnabled && !pickupNo"')
  const z = r.indexOf('<template v-else>')
  return a === -1 || z === -1 ? '' : r.slice(a, z)
}
const s5Region = () => {
  const r = couponRegion()
  const a = r.indexOf('<template v-else>')
  return a === -1 ? '' : r.slice(a)
}
// 组件声明的 emits array（不是 template 里的 $emit 调用——那会重复计数）。
const declaredEmits = () => {
  const block = (SCRIPT.match(/emits:\s*\[([\s\S]*?)\]/) || [, ''])[1]
  return (block.match(/['"][^'"]+['"]/g) || []).map((q) => q.slice(1, -1))
}

describe('PaymentSuccessSheet 低熵交易状态合同', () => {
  it('主轴是「成功 + 金额确认 + 实时订单状态」，标题不做 payment-mode 推断', () => {
    expect(TEMPLATE).toContain('{{ successText.title }}')
    // 金额是 display-only binding，不允许组件内重新计算
    expect(TEMPLATE).toContain('{{ paidLabel }}')
    expect(TEMPLATE).toContain('{{ successTotal.toFixed(2) }}')
    // 实时订单状态必须仍在首屏（不允许移进折叠 / 详情）
    expect(TEMPLATE).toContain('{{ successStatusText }}')
    expect(TEMPLATE).toMatch(/class="order-status-bar"[\s\S]{0,40}:class="successStatusTone"/)
    // 统一「下单成功」——不得按 paidLabel / paymentMode 做 mode-aware 标题分支
    expect(TEMPLATE).not.toContain('successPaymentMode')
    expect(TEMPLATE).not.toContain('paymentMode')
    expect(TEMPLATE).not.toMatch(/paidLabel\s*===?/)
  })

  it('防重复提交 / 支付提示保留，并入状态组，不再单独 footer', () => {
    expect(TEMPLATE).toMatch(/状态自动更新\s*·\s*请勿重复提交或支付/)
    // 旧的独立底部说明不允许回归
    expect(TEMPLATE).not.toContain('class="success-safe-tip"')
    expect(TEMPLATE).not.toContain('successText.safeTip')
  })

  it('系统元数据不重新回到成功页首屏（对应业务字段仍留在 props）', () => {
    // 订单号 / 商品件数 不再在成功页展示
    expect(TEMPLATE).not.toContain('successText.orderNo')
    expect(TEMPLATE).not.toContain('successOrderNo')
    expect(TEMPLATE).not.toContain('successText.items')
    expect(TEMPLATE).not.toContain('successOrderItemCount')
    // 积分余额不在成功页展示（只审 template，不动 script 的业务数据）
    expect(TEMPLATE).not.toContain('points_balance')
    // 但对应 prop / 契约必须仍然存在——这是 REMOVE_FROM_PRESENTATION，不是删业务
    expect(SCRIPT).toContain('successOrderNo')
    expect(SCRIPT).toContain('successOrderItemCount')
    expect(SCRIPT).toContain('points_balance')
  })

  it('桌牌状态单一来源：待领取 / 已分配互斥，旧大号 hero 不回归', () => {
    // 待领取：条件 + 文案
    expect(TEMPLATE).toContain('v-if="pickupNoEnabled && !pickupNo"')
    expect(TEMPLATE).toContain('桌牌待领取')
    expect(TEMPLATE).toContain('请向工作人员领取桌牌')
    // 已分配：条件 + 单行「桌牌 N 号」
    expect(TEMPLATE).toContain('v-if="pickupNoEnabled && pickupNo"')
    expect(TEMPLATE).toMatch(/桌牌[\s\S]{0,80}\{\{ pickupNo \}\}[\s\S]{0,8}号/)
    // 旧 hero 不允许回归
    expect(TEMPLATE).not.toContain('pickup-hero')
    expect(TEMPLATE).not.toContain('您的桌牌号')
  })

  it('会员奖励是低熵单行，gate 语义不变，不展示积分余额', () => {
    // 权威 gate 保持：status available 且 (savings>0 或 points_earned>0)
    expect(TEMPLATE).toMatch(
      /memberValue\.status === 'available'[\s\S]{0,80}member_savings > 0[\s\S]{0,40}points_earned > 0/,
    )
    expect(TEMPLATE).toContain('会员本单省 ¥')
    expect(TEMPLATE).toMatch(/\+\{\{ memberValue\.points_earned \}\}积分/)
    // savings + points 两半各自 >0 守卫（防止 ¥0 / +0积分 的零价值文案）
    expect(TEMPLATE).toContain('v-if="memberValue.member_savings > 0 && memberValue.points_earned > 0"')
  })

  it('优惠券两个 presentation 分支各自：不造假「查看」动作、且保留 reminder', () => {
    // gate 不变
    expect(TEMPLATE).toContain('v-if="earnedCoupon"')
    const region = couponRegion()
    const s6 = s6Region()
    const s5 = s5Region()
    // 三段都被结构性定位到（若券块或某分支被删，这里先炸）
    expect(region.length).toBeGreaterThan(0)
    expect(s6.length).toBeGreaterThan(0)
    expect(s5.length).toBeGreaterThan(0)
    // 分支各自的券文案
    expect(s6).toContain('已获券')
    expect(s5).toContain('已获优惠券')
    // 每个分支「独立」禁止假的跳转类文案——只在 coupon 分支范围内断言，
    // 绝不全局 ban「查看」（合法的「查看本桌订单」在券区之外）
    for (const branch of [s6, s5]) {
      for (const fake of ['查看', '详情', '去使用', '去看看', 'navigateTo', 'navigateBack']) {
        expect(branch).not.toContain(fake)
      }
    }
    // 每个分支「独立」保留 reminder：删任一分支的 reminder 都会让对应断言 FAIL
    expect(s6).toContain("$emit('request-coupon-reminder')")
    expect(s5).toContain("$emit('request-coupon-reminder')")
    expect(s6).toContain('提醒我')
    expect(s5).toContain('提醒我')
  })

  it('后续操作层级固定为 查看本桌订单 → 继续加菜 → 关闭', () => {
    const primary = TEMPLATE.indexOf("$emit('view-order-detail')")
    const secondary = TEMPLATE.indexOf("$emit('continue-ordering')")
    const close = TEMPLATE.indexOf("$emit('close-and-wait')")
    expect(primary).toBeGreaterThan(-1)
    expect(secondary).toBeGreaterThan(-1)
    expect(close).toBeGreaterThan(-1)
    expect(primary).toBeLessThan(secondary)
    expect(secondary).toBeLessThan(close)
    // 结构归属：primary = 查看本桌订单，secondary = 继续加菜，tertiary(关闭) = ghost
    expect(TEMPLATE).toMatch(/class="success-btn-primary"[\s\S]{0,80}\$emit\('view-order-detail'\)/)
    expect(TEMPLATE).toMatch(/class="success-btn-secondary"[\s\S]{0,80}\$emit\('continue-ordering'\)/)
    expect(TEMPLATE).toMatch(/class="success-btn-ghost"[\s\S]{0,80}\$emit\('close-and-wait'\)/)
    expect(TEMPLATE).toMatch(/class="success-btn-ghost"[\s\S]{0,120}关闭/)
  })

  it('emits 恰为 4 个既有事件，且 legacy overlay 合同不变', () => {
    const emits = declaredEmits()
    // 锁「数量 = 4」+「集合完全一致」——任何未知的第 5 个 emit（share-order /
    // track-order / open-help …）或改名都会让这里 FAIL；引号 / 换行 / formatter
    // 变化不影响（只比对事件名集合，不比对原始字符串）
    expect(emits).toHaveLength(4)
    expect([...emits].sort()).toEqual(
      ['close-and-wait', 'continue-ordering', 'request-coupon-reminder', 'view-order-detail'].sort(),
    )
    // legacy mask overlay 保留（本 candidate 不迁 BaseSheet）
    expect(TEMPLATE).toContain('class="mask success-mask"')
    expect(TEMPLATE).not.toContain('<base-sheet')
  })
})
