import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(here, '../../../')
const read = (rel) => readFileSync(path.join(srcRoot, rel), 'utf8')

// 确认订单 和 本桌订单 是同一张"点单卡"——顾客在"下单前确认"和"回来看订单"
// 两处看到的必须是同一个视觉，不是两套长得像的东西。做法是共用
// table-order-card.scss 的 `.to-*` 骨架，CheckoutSheet 只加确认页专属的可编辑控件。

describe('CheckoutSheet 复用「本桌订单」的 .to-* 点单卡', () => {
  const checkout = read('subpkg-order/components/CheckoutSheet.vue')
  const menu = read('subpkg-order/pages/menu.vue')

  it('直接 import 共用样式表——不再自己拷一份卡片 CSS', () => {
    expect(checkout).toMatch(/@import\s+['"]\.\/table-order-card\.scss['"]/)
  })

  it('卡片骨架用 .to-* 类，跟 TableBillSheet 同一套', () => {
    for (const cls of [
      'class="to-card"',
      'class="to-plate"',
      'class="to-plate-table"',
      'class="to-plate-unit"',
      'class="to-divider"',
      'class="to-list"',
      'class="to-drow"',
      'class="to-drow-img"',
      'class="to-drow-main"',
      'class="to-drow-name"',
      'class="to-line to-line--sub"',
      'class="to-foot"',
      'class="to-foot-v"',
      'class="to-detail"',
      'class="to-detail-head"',
      'class="to-detail-t"',
    ]) {
      expect(checkout).toContain(cls)
    }
  })

  it('不再有旧的一次性卡片类（已被 .to-* 取代）', () => {
    for (const dead of [
      'class="order-summary-card"',
      'class="member-summary-card"',
      'class="confirm-card price-summary-card"',
      'class="checkout-main-card"',
      'class="checkout-table-plate"',
      'class="checkout-table-number"',
      'class="checkout-divider"',
      'class="checkout-total-area"',
      'class="checkout-details-card"',
      'class="checkout-details-title"',
      'Georgia',
    ]) {
      expect(checkout).not.toContain(dead)
    }
  })

  it('确认订单收敛为交易主线（B 版低熵信息架构）', () => {
    // 顾客进确认页只回答三件事：点了什么 / 有没有点错 / 付多少钱。
    // CHECKOUT-02 冻结的 B 版把没有交易信息增量的展示删掉——以下旧高熵结构不得回归：
    for (const gone of [
      'class="checkout-plate-meta"',     // 桌牌下 堂食 · 会员 · 预计积分 · N张可用
      'class="checkout-item-selected"',  // 装饰性绿 ✓ 圈（无 selection 语义，cart item 恒提交）
      'class="checkout-item-subtotal"',  // 逐行小计（= 单价 × 数量 的重复）
      'class="checkout-items-amount"',   // 已选商品头右侧重复的商品原价
    ]) {
      expect(checkout).not.toContain(gone)
    }
    // 总份数只在商品头出现一次；应付行不再带「共 N 份 ·」前缀
    expect(checkout).toMatch(/已点商品\s*·\s*\{\{\s*totalCount\s*\}\}\s*份/)
    expect(checkout).not.toMatch(/共\s*\{\{\s*totalCount\s*\}\}\s*份\s*·/)
    // 无优惠且无可用券时优惠券行整行不渲染——「暂无可用」常驻分支已删
    expect(checkout).not.toContain('confirmationText.couponNone')

    // B 版条件展示合同：原价行 / 优惠券行 只在有信息价值时出现
    expect(checkout).toMatch(/v-if="discountAmount > 0"[\s\S]{0,40}class="to-line to-line--sub"/)
    expect(checkout).toMatch(/v-if="discountAmount > 0 \|\| availableCoupons\.length > 0"[\s\S]{0,160}class="to-line checkout-coupon-line"/)

    // 交易主线控件继续受保护（数量步进器 + 单一提交 CTA）
    expect(checkout).toContain('class="checkout-item-counter"')
    expect(checkout).toContain('class="checkout-btn-full"')
  })

  it('提交按钮尺寸对齐本桌订单的主按钮（92rpx / 46rpx 胶囊 / 无阴影）', () => {
    expect(checkout).toMatch(/\.checkout-btn-full\s*\{[\s\S]*?height:\s*92rpx/)
    expect(checkout).toMatch(/\.checkout-btn-full\s*\{[\s\S]*?border-radius:\s*46rpx/)
    expect(checkout).not.toMatch(/\.checkout-btn-full\s*\{[\s\S]*?box-shadow:/)
  })

  it('弹层底色跟本桌订单一致（浅灰，卡片浮在上面）', () => {
    expect(checkout).toMatch(/\.order-confirm-sheet\s*\{[^}]*background:\s*var\(--bg-subtle\)/)
  })

  it('每个既有动作的 emit 合同一字不改', () => {
    for (const event of [
      'show-table-hint',
      'toggle-items-expanded',
      'remove-from-cart',
      'increase-cart-item',
      'clear-cart',
      'toggle-order-remark-expanded',
      'toggle-remark-chip',
      'show-order-remark-extra',
      'update:remark',
      'open-coupon-picker',
      'checkout',
    ]) {
      expect(checkout).toContain(`'${event}'`)
    }
    expect(checkout).toMatch(/layer=["']blocking["']/)
    expect(checkout).toContain('<template #footer>')
  })

  it('滚动区给显式 max-height（mp-weixin 的 scroll-view 不认 flex 推算的高度，长列表会滚不动）', () => {
    const block = checkout.match(/\.order-confirm-content\s*\{([\s\S]*?)\}/)
    expect(block).not.toBeNull()
    expect(block[1]).toMatch(/max-height:\s*calc\([^)]*vh[\s\S]*env\(safe-area-inset-bottom\)/)
    // flex:1 / height:0 的老写法不能再有——那是这次卡死的根因
    expect(block[1]).not.toMatch(/\bheight:\s*0;/)
    expect(block[1]).not.toMatch(/\bflex:\s*1;/)
  })

  it('打开确认弹层时清单默认展开', () => {
    expect(menu).toMatch(/showCart\.value\s*=\s*true[\s\S]{0,180}itemsExpanded\.value\s*=\s*true/)
    expect(menu).toContain('const toggleItemsExpanded = () => { itemsExpanded.value = !itemsExpanded.value }')
  })

  it('没有引入请求 / 公开 API 字段的改动', () => {
    expect(checkout).not.toMatch(/\b(activityId|userId|couponId|storeId|campaign_id|activity_id)\b/)
    expect(checkout).not.toMatch(/\b(fetch|request|axios)\s*\(/)
  })
})
