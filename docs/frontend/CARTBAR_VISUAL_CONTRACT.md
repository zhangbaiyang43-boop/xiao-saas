# P1-CARTBAR-VISUAL-CONTRACT-PHASE-01

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
BASELINE=6eea43f
SCOPE=CartBar.vue / menu.vue / CheckoutSheet.vue / PaymentSuccessSheet.vue
CODE_CHANGE=NO
NEW_COMPONENT=NO
NEW_TOKEN=NO
AUTHORITY=本文件只记录 CartBar 的产品定位与视觉事实，不是 AppButton，不是新 token
SOURCE=
  member-mini-client/src/subpkg-order/components/CartBar.vue
  member-mini-client/src/subpkg-order/pages/menu.vue
  member-mini-client/src/subpkg-order/components/CheckoutSheet.vue
  member-mini-client/src/subpkg-order/components/PaymentSuccessSheet.vue
  docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md
  docs/frontend/HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md
  docs/frontend/PAYMENT_SUCCESS_OVERLAY_DECISION.md
```

只审计。不改代码、不创建组件、不新增 token。  
`HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md` 仍是 OPEN（主 CTA 家族 / 深色方案未拍板）。本文把 **CartBar 是什么** 从实现里钉死，避免下一阶段把它误当成导航、订单入口或结算付款按钮。

---

## 0. 结论（从实现反推，不是新设计）

| 问 | 结论 |
|---|---|
| CartBar 产品定位 | **点餐 Tab 上的购物车摘要 + 打开确认单的入口。** 不是导航，不是订单状态入口，也不是付款按钮。 |
| 当前视觉 | 深色强调条，叠在白 BottomNav 之上；有货时白字 48rpx 合计 + 绿胶囊「去结算」。 |
| 与 Checkout CTA | **两步、两种按钮。** CartBar「去结算」只 `openCart`；Checkout footer 才真正提交/支付。 |
| 是否进入未来 CTA 体系 | **条本身不进。** 只有右侧胶囊若将来做 CTA 家族，归「Chrome 入口胶囊」，**禁止**和结算/成功页满宽提交按钮并成一套。 |

---

## 1. 产品定位

CartBar 只在点餐 Tab 出现：`menu.vue` L175–L185 `v-show="activeTab === 'order'"`。首页 / 会员卡 / 我的没有这条。

唯一事件：`open-cart`。左区（有货时）和右区「去结算」都 emit 同一个事件（`CartBar.vue` L3、L29）。`menu.vue` `openCart`（L1181–L1197）只做：

- `showCart = true`（打开 `CheckoutSheet`）
- 展开已选：件数 ≤ 1 时默认展开
- 顺手刷新设置/券，**不等网络**

它不提交订单、不调支付、不打开本桌订单、不切 Tab。

对照同一页上的其它底栏：

| 表面 | 是什么 | 证据 |
|---|---|---|
| **BottomNav** | 导航 | 四 Tab：home / order / card / mine（`BottomNav.vue`）。CartBar 出现时它仍在。有货时点餐 Tab 上有绿点（L8），那是导航提示，不是 CartBar。 |
| **CartBar** | 购物车入口 chrome | 固定在 BottomNav 上方；文案「去结算」；动作是开确认单。 |
| **CheckoutSheet footer** | 提交/付款 CTA | `emit('checkout')` → `goCheckout`。按钮文案随支付态变化（`payButtonText`，`menu.vue` L930–L941：立即支付 / 提交到桌台账单 / 正在支付…）。 |
| **OrderBubble** | 订单状态入口 | `menu.vue` L161–L170：未终态才显示；点击 `viewOrderDetail` 开本桌 Sheet。`bottom-clear-rpx="268"` 是为了避开 CartBar+Nav。 |
| **PaymentSuccessSheet** | 独立结果型底部 Sheet | 已冻结：点遮罩不能关；主动作「关闭并等待」。与 CartBar 无交互。 |

空车时「去结算」是 disabled，左区点击为空（L3 `totalCount > 0 ? emit : null`）。空车条仍占位，不是入口。

因此三个备选里：

- **导航？否。** 导航是 BottomNav。CartBar 不切页面。
- **CTA？只对右侧胶囊成立，而且是「打开确认单」的入口 CTA，不是付钱。** 整条 CartBar 是 chrome，不是一个按钮。
- **订单状态入口？否。** 那是 OrderBubble / 成功页「查看本桌订单」。CartBar 不读 `myOrders` / `pendingOrderCount`。

---

## 2. 当前视觉（事实，不是规范）

全部来自 `CartBar.vue`，除非另注。

### 条

| 项 | 值 |
|---|---|
| 位置 | `position: fixed`；`bottom: calc(100rpx + env(safe-area-inset-bottom))`（L65）= BottomNav 高度之上 |
| 条高 | `148rpx + safe-area`（L68–L69）；内边距底再加一份 safe（L74） |
| z-index | **320** 字面量（L64）。`--z-chrome` 是 300（BottomNav 已改成 token）。320 没有 token，夹在 chrome 与 floating 之间，为了压过 BottomNav，并让 CouponBar 催用条 319 贴在它上面 |
| 空车底 | `#1f2937`（L75） |
| 有货底 | `var(--text-1)` = `#111827`（L79） |
| 阴影 | `0 -6rpx 20rpx rgba(0,0,0,0.18)`（L76） |

列表要自己垫高：`DishList.vue` `.list-pad` = `348rpx + safe`，给 CartBar + BottomNav 留空。这是布局耦合，不是 spacing token。

### 图标 / badge

| 项 | 空车 | 有货 |
|---|---|---|
| 圆 | 96rpx，`#4B5362` | 同尺寸，`var(--brand)` |
| 角标 | 无 | `#F04444`，22rpx；文案来自 `cartBadgeText`（>99 显示 `99+`） |

`#4B5362` / `#F04444` 都不是 token（接近但不是 `--danger` `#ef4444`）。

### 「去结算」胶囊

| 项 | 值 |
|---|---|
| 高度 | **92rpx** |
| 圆角 | **46rpx**（胶囊） |
| 字 | 32rpx / **600** / 白 |
| 底 | `var(--brand)`；绿光 `rgba(7,193,96,0.35)` |
| Disabled | `#4B5362`，白字 0.45 透明，无阴影 |

字号 32 / 字重 600 碰巧等于 `--btn-primary-font-*`，但高度 92 ≠ token 100，圆角 46 ≠ 50。CartBar **没有**走 `--btn-primary-*`。

### 金额层级

| 角色 | 字号 / 字重 / 色 | 路径 |
|---|---|---|
| 条上合计 | **48rpx / 700 / `#fff`**；脉冲时 `#34f38a` | `CartBar.vue` L15、L146–L157、L239–L241 |
| 份数 | 24rpx / 白 0.62 | L160–L166 |
| 空车文案 | 30rpx / 600 / 白 0.72 | L170–L179 |
| 菜卡价 | PriceText md：40rpx / 700 / `--brand` | DishList（范围外，对照用） |
| 结算已选合计 | 34rpx / 900 / `--brand` | CheckoutSheet L29 |
| 结算应付 | **52rpx / 900 / `--brand`** | CheckoutSheet L355–L356 |
| 成功实付 | 68rpx / 900 / `#111` | PaymentSuccessSheet |

条上合计是路径里唯一的 **深底白字大价**。它不是 PriceText（PriceText 只有绿字 sm/md/lg）。48rpx 比菜卡大、比结算应付小、比成功实付小。层级是：菜卡价 < 车内合计 < 应付 < 实付。

点击反馈：CartBar 主 CTA **没有** `.tap-shrink`。加购有脉冲（图标 / badge / 金额）。

---

## 3. 与 Checkout CTA 的关系

两步必须分开：

```
点餐列表
  → CartBar「去结算」     打开 CheckoutSheet（确认）
  → Checkout「立即支付…」  提交 / 拉起支付
  → PaymentSuccessSheet   结果（关闭并等待 / 继续加菜 / 查看本桌订单）
```

| | CartBar `.checkout-btn` | Checkout `.checkout-btn-full` | Success `.success-btn-primary` |
|---|---|---|---|
| 动作 | `openCart`，开确认单 | `checkout` → `goCheckout` | `close-and-wait`，关结果 sheet |
| 文案 | 固定「去结算」 | `payButtonText`（立即支付 ¥x / 提交到桌台账单 / 正在…） | 「关闭并等待」 |
| 高 | 92rpx | **104rpx** | 98rpx |
| 圆角 | 46rpx 胶囊 | **28rpx** 偏方 | `--radius-card` 24rpx |
| 字重 | 600 | **900** | 900 |
| 所在底 | 深色条 | 浅色 BaseSheet footer | 结果型底部 Sheet 内卡 |
| Disabled | `#4B5362`（深灰） | `#cbd5e1`（浅灰） | 无 disabled |

同名前缀 `checkout-btn*` 容易让人以为是同一个按钮。实现上不是：一个开 sheet，一个付钱。成功页主按钮已经冻结为「等待」，更不是结算提交。

金额也不在同一组件里传递：CartBar 展示 `totalPrice`（货品合计）；Checkout 应付是 `wechatPayAmount`（扣券后）。条上没有券后价。

---

## 4. 是否进入未来 CTA 体系

`--btn-primary-*`（100 / 50 / 32 / 600）只被 SpecSheet 确认按钮采用。Constitution：新主 CTA 用这组 token；AppButton 是 Deferred。

三层东西不要混：

1. **CartBar 条**（深色 148rpx chrome，z 320）  
   **不进 CTA 体系。** 它是底栏结构，和按钮 token 无关。改成浅色/并进 `--bg-card` 是 `HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md` 决策 2，本文不重开、不采纳。

2. **CartBar「去结算」胶囊**  
   若未来有 CTA 家族，它属于先前文档建议的 **Chrome 入口胶囊**（深底上的绿胶囊、打开下一步），**不要**改成 Checkout 那种满宽 104rpx / 28rpx / 900。动作不同，形状不同是合理的。

3. **Checkout / Success 满宽提交或结果主按钮**  
   Sheet 内提交/结果按钮。成功页已冻结为结果型底部 Sheet，主按钮不是「去结算」。它们若进 CTA 体系，是另一套 **Sheet 满宽按钮**，与 CartBar 胶囊分家。

因此：**CartBar 整条不进未来 CTA 体系；右侧胶囊最多作为 Chrome 入口的一个实例，且须等 CTA 家族真正拍板。** 在那之前维持 92 / 46 / 600，禁止借「统一按钮」改高度或改成方按钮。

PriceText：条上白字 48rpx 对不上 sm/md/lg，也没有 inverse 档。扩档 ≈ 新 API，本审计禁止。金额继续手写。

z-index 320：没有对应 layer token。本审计禁止新增 token。维持 320，直到 layer 合同单独扩展。

---

## 5. 本文钉死 vs 仍 OPEN

**从实现钉死（下一阶段不得装糊涂）：**

- CartBar = 点餐 Tab 购物车入口 chrome，不是导航、不是本桌订单入口、不是付款按钮。
- 「去结算」只打开 CheckoutSheet。
- 付款/提交只发生在 Checkout footer。
- 成功页是结果型底部 Sheet，主按钮「关闭并等待」，与 CartBar 无关。
- 深色条 + 白字合计 + 绿胶囊，是当前有货态的视觉事实。

**仍 OPEN（`HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md`，本文不拍）：**

- 深色条是否永久保留。
- Chrome 胶囊 vs Sheet 满宽是否正式分成两套，以及各套高度。
- 48rpx 白字合计是否进 PriceText。
- 320 / 319 是否并入 layer token。

---

## 6. 本阶段没做

- 没有改 CartBar / menu / Checkout / Success 的任何样式或逻辑。
- 没有创建 AppButton，没有新增 token。
- 没有把 OPEN 的 CTA 家族写成现行规范。
- 没有在模拟器里目测；结论来自源码。
