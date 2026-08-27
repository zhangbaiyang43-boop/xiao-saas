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

  it('只保留确认页专属的可编辑控件 / 信息', () => {
    for (const cls of [
      'class="checkout-item-selected"',   // 选中圈（本桌订单那里是四点进度）
      'class="checkout-item-counter"',    // 加减步进器
      'class="checkout-item-subtotal"',   // 小计
      'class="checkout-plate-meta"',      // 桌牌下方 堂食 · 会员
      'class="checkout-btn-full"',        // 单个提交 CTA
    ]) {
      expect(checkout).toContain(cls)
    }
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

  it('滚动区用 flex:1 + min-height:0（不加 height:0——那会让 footer 被挤出安全区）', () => {
    expect(checkout).toMatch(/\.order-confirm-content\s*\{[\s\S]*?\n\s*flex:\s*1;[\s\S]*?\n\s*min-height:\s*0;/)
    expect(checkout).not.toMatch(/\.order-confirm-content\s*\{[\s\S]*?\n\s*height:\s*0;/)
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
