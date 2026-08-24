# P1-HIGH-FREQUENCY-UI-CONSOLIDATION-PHASE-01

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
BASELINE=b90ccb5
SCOPE=顾客端高频路径：首页 / 菜单 / 购物车 / 结算 / 支付成功
CODE_CHANGE=NO
NEW_COMPONENT=NO
NEW_TOKEN=NO
AUTHORITY=
  member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md
  docs/frontend/DESIGN_SYSTEM_CURRENT.md
  docs/frontend/DESIGN_SYSTEM_ADOPTION_AUDIT.md
  member-mini-client/src/styles/global.scss
```

对照已有 token / primitive / Constitution，量这条路径「看起来是不是同一套 UI」。不发明新规范、不设计新组件、不新增 token。

缺口分两类：

| 标记 | 含义 |
|---|---|
| **SPEC_GAP** | 仓库里已经有名字的规则没被这条路径用上，或同一元素仍有历史第二套。 |
| **DECISION** | Constitution Deferred，或源码里没有合同。后续要先做设计决策，不能假装「漏用了某个已有 token」。 |

本文不把 Deferred 写成「现在就要造」。

---

## 0. 路径地图（本阶段范围）

五步都活在同一页：`member-mini-client/src/subpkg-order/pages/menu.vue`。不是独立路由。

| 用户步骤 | 实际表面 | 文件 |
|---|---|---|
| 首页 | 底栏 `home` Tab | `subpkg-order/components/HomeTab.vue`；顶栏仍是 `ShopHeader.vue`；底栏 `BottomNav.vue` |
| 菜单 | 底栏 `order` Tab | `ShopHeader.vue` + `CouponBar.vue` + `DishList.vue`；选规格 `SpecSheet.vue`；加载 `LoadingStates.vue` |
| 购物车 | 菜单底常驻条 | `CartBar.vue`（点击「去结算」打开下一层，没有独立购物车页） |
| 结算 | 确认订单底栏弹层 | `CheckoutSheet.vue`；叠层 `CouponPicker.vue` / `CheckoutAuthSheet.vue` / `MemberCheckoutChoice.vue` |
| 支付成功 | 成功底栏弹层 | `PaymentSuccessSheet.vue` |

不在本阶段：进店页 `pages/index`、会员 Tab `MemberCard`、我的 `pages/mine`、本桌订单 `OrderHistorySheet` / `TableBillSheet`、欢迎券 `WelcomeCouponSheet`。它们会在 `menu.vue` 里同时存在，但本文不审视觉。

基线 `b90ccb5` 已完成 Overlay 合同、颜色 token、State* 品牌色、会员/券 `--brand`。Button / Card / Type / Spacing primitive 仍未建立（Constitution Deferred）。

---

## 1. Button 一致性

**已有合同（仅此）：** `global.scss` L29–L32 `--btn-primary-height: 100rpx` / `--btn-primary-radius: 50rpx` / `--font-size: 32rpx` / `--font-weight: 600`。命名 primitive 还有 `AddBtn.vue`（绿圆加号）。没有 AppButton。

**本路径真正走 `--btn-primary-*` 的只有规格确认：** `SpecSheet.vue` L520–L536。

| 表面 | 选择器 | 高 | 圆角 | 字号 / 字重 | 底色 | 路径 |
|---|---|---|---|---|---|---|
| 首页 Hero CTA | `.ht-order-btn` | 100rpx | 50rpx | 34rpx / 800 | 白底绿字（反相） | `HomeTab.vue` L265–L278 |
| 首页招牌加入 | `.ht-feature-add` | 72rpx | 36rpx | 26rpx / 800 | `--brand` | `HomeTab.vue` L423–L439 |
| 菜单选规格 | `.choose-option-btn` | 60rpx | 30rpx | 24rpx / 600 | `--brand` | `DishList.vue` L710 |
| 菜单空态重试 | `.empty-retry` | 72rpx | 36rpx | 28rpx / 700 | `--brand` | `DishList.vue` L695–L706 |
| 菜单加号 | `.dish-counter .counter-btn` | 60rpx 圆 | 50% | icon 27rpx | `--brand` | `DishList.vue` L635–L640 |
| AddBtn md（本路径未用） | `.add-btn--md` | 72rpx 圆 | 50% | 30rpx | `--brand` | `AddBtn.vue` L44–L48；消费者只有 SpecSheet |
| 购物车去结算 | `.checkout-btn` | 92rpx | 46rpx | 32rpx / 600 | `--brand` | `CartBar.vue` L183–L197 |
| 结算提交 | `.checkout-btn-full` | 104rpx | 28rpx | 34rpx / 900 | `--brand` | `CheckoutSheet.vue` L372 |
| 成功主按钮 | `.success-sheet .success-btn-primary` | 98rpx | `--radius-card`（24rpx） | 32rpx / 900 | `--brand` | `PaymentSuccessSheet.vue` L662–L675 |
| 成功次按钮 | `.success-sheet .success-btn-secondary` | 94rpx | `--radius-card` | 30rpx / 800 | 白 + `#dfe5e8` 边 | `PaymentSuccessSheet.vue` L679–L692 |
| 成功幽灵按钮 | `.success-sheet .success-btn-ghost` | 68rpx | 20rpx（未覆盖的 L317） | 26rpx / 700 | 透明 | `PaymentSuccessSheet.vue` L696–L706 |
| 规格确认 | `.spec-confirm-btn` | token 100rpx | token 50rpx | token 32/600 | `--brand` | `SpecSheet.vue` L520–L536 |
| 菜单错误重试 | `.retry-btn` | padding 16/48（无固定高） | `--radius-card` | 30rpx / 700 | `--brand` | `LoadingStates.vue` L157–L167 |
| StateEmpty/Error 按钮（本路径未用） | `.state-*-btn` | 88rpx | 24rpx | 30rpx / 600 | `--brand` | `state-empty.vue` L51–L66；`state-error.vue` L40–L55 |

Disabled 也不是一套：

| 表面 | Disabled 底 | 路径 |
|---|---|---|
| 首页招牌加入 | `#D0D5DD` | `HomeTab.vue` L443 |
| 购物车空 | `#4B5362`（深色底栏上的灰） | `CartBar.vue` L199–L202 |
| 结算不可提交 | `#cbd5e1` | `CheckoutSheet.vue` L375 |
| 规格不可确认 | `#cfd6dc` | `SpecSheet.vue` L540–L543 |

点击反馈：公共类 `.tap-shrink`（`global.scss` L48–L54）在这条路径上几乎只有 `CouponBar.vue` L2/L9。HomeTab 自写 `scale(0.992)` / `scale(0.96)`（L219、L436）；DishList 选规格 `scale(.97)`（L713）；CartBar / CheckoutSheet / PaymentSuccessSheet 主 CTA 没有按下缩放。

### SPEC_GAP

- 结算、购物车、支付成功、首页 Hero、菜单选规格 **都没有** 使用已有 `--btn-primary-*`。唯一采用点是 SpecSheet。
- 菜单加号 **没有** 使用已有 `AddBtn`；DishList 自写 60rpx 圆，和 AddBtn md 72rpx、`_shared.scss` `.counter-btn` 72rpx（L20–L24）三套并存。CheckoutSheet 行内加减走 `_shared.scss` `.counter-btn.sm`（模板 L42–L44）。
- `.tap-shrink` 已是公共点击反馈，高频 CTA 多数不用。

### DECISION

- 主按钮「标准高度」未定。现状同时存在 60 / 72 / 88 / 92 / 94 / 98 / 100 / 104 rpx。`--btn-primary-height: 100rpx` 只是 SpecSheet 回溯值，**不是** 全路径已采纳的视觉标准。
- 胶囊（50rpx / 46rpx / 36rpx）vs 卡片圆角（28rpx / `--radius-card` 24rpx）未定哪套是主 CTA。CartBar 胶囊、CheckoutSheet 偏方、成功页用 `--radius-card`，三步相邻、三种形状。
- 首页 Hero 白底绿字（反相）是否算「同一主按钮家族」未定。尺寸碰巧对齐 token，颜色和字重（800 vs token 600）不是同一合同。
- 字重 600 / 700 / 800 / 900 哪档属于主 CTA，没有合同。
- AppButton 本身是 Constitution Deferred，本阶段禁止新建。

---

## 2. Card 结构

**已有合同：** `global.scss` L65–L70 `.card-base` = `background: var(--bg-card)` + `border-radius: var(--radius-card)` + `box-shadow: var(--card-shadow)`。`--radius-card: 24rpx`，`--radius-hero: 36rpx`，`--card-shadow: 0 4rpx 16rpx rgba(17,24,39,0.06)`。

本路径 **零引用** `.card-base`。

| 表面 | 圆角 | 阴影 | 底 | 路径 |
|---|---|---|---|---|
| 首页营业状态卡 | **32rpx**（两档 token 都不是） | `0 8rpx 24rpx rgba(17,24,39,0.04)` 不是 `--card-shadow` | `#fff` 硬编码 | `HomeTab.vue` L145–L156 |
| 首页点餐 Hero | **36rpx**（值等于 `--radius-hero`，未写 token） | 无 | `--brand` + 背景图 | `HomeTab.vue` L207–L215 |
| 首页招牌菜卡 | **32rpx** | 无 | `#fff` | `HomeTab.vue` L325–L332 |
| 菜单菜卡 | `--radius-card` ✓ | `--card-shadow` ✓ | `#fff` | `DishList.vue` L437–L453 |
| 菜单缩略图 | **20rpx** | `0 2rpx 8rpx rgba(17,24,39,0.08)` | `#F5F3EE` | `DishList.vue` L466–L477 |
| 菜单再来一单条 | **20rpx** | `--card-shadow` ✓ | `#fff` | `DishList.vue` L496–L508 |
| 结算桌台条 | `--radius-card` ✓ | 无；`1rpx solid #cbeedb` | `#ecfbf3` | `CheckoutSheet.vue` L196 |
| 结算会员条 | `--radius-card` ✓ | 无 | `#f0f7ff` / `#f8fafc` | `CheckoutSheet.vue` L202–L222 |
| 结算内容卡 | `--radius-card` ✓ | 无；`1rpx solid #eef1f3` | `#fff` | `CheckoutSheet.vue` L245 |
| 结算弹层外壳 | **32rpx 32rpx 0 0** | 无 | `#f5f7f8`（接近但不是 `--bg-page` `#f5f6fa`） | `CheckoutSheet.vue` L169–L177 |
| 成功弹层外壳 | **32rpx 32rpx 0 0** | 无 | `--bg-subtle` | `PaymentSuccessSheet.vue` L336–L344 |
| 成功内卡 | **28rpx**（覆盖更早的 40rpx） | 无；`1rpx solid #edf0f2` | `--bg-card` | `PaymentSuccessSheet.vue` L141–L148 被 L357–L366 覆盖 |
| 成功券卡 | **24rpx**（值等于 `--radius-card`，未写 token） | 红金投影 | 券红渐变（Constitution 允许） | `PaymentSuccessSheet.vue` L483–L494 |
| 规格弹层外壳 | **40rpx 40rpx 0 0** | — | — | `SpecSheet.vue` L151 |

结构也不统一：首页是「大 Hero + 横向图文卡」；菜单是「左图右文固定 236rpx 高」；结算是「白底分区卡 + 行」；成功是「居中仪式卡嵌在底栏 sheet 里」。这不是漏用 `.card-base` 能单独修完的。

### SPEC_GAP

- `.card-base` 已定义，本路径零采用。
- 首页 Hero 圆角 36rpx 等于 `--radius-hero` 却手写。成功券卡 24rpx 等于 `--radius-card` 却手写。
- 首页状态卡 / 招牌卡用 32rpx + 自制阴影，绕开已有 `--radius-card` / `--card-shadow`。
- 菜卡本身是本路径里 **最接近** `.card-base` 的表面（`DishList.vue` L448–L449），但缩略图仍 20rpx。
- 结算弹层底 `#f5f7f8` 未走 `--bg-page` / `--bg-subtle`。

### DECISION

- 32rpx / 20rpx / 28rpx / 40rpx 要不要并进现有两档（24 / 36），还是承认第三档。Constitution 明确 radius 完整档是 Deferred。
- 底栏 sheet 顶角：Checkout/Success 32rpx、SpecSheet 40rpx、BaseSheet 也是 32rpx（不在本路径）。未定「标准 sheet 顶角」。
- 卡片用阴影（菜卡）还是描边（结算 `1rpx #eef1f3`）未定。
- 首页 Hero 是否允许脱离卡片家族（全幅品牌图）是产品/视觉决策，不是漏用 token。

---

## 3. Price 展示

**已有 primitive：** `PriceText.vue`（Constitution 点名）。三档：

| size | ¥ | 金额 | 后缀 | 色 |
|---|---|---|---|---|
| sm | 22rpx | 30rpx | 20rpx | `--brand` / 700 |
| md | 24rpx | 40rpx | 22rpx / 500 | 同上 |
| lg | 28rpx | 44rpx | 24rpx | 同上 |

本路径 **唯一消费者是 SpecSheet**。首页 / 菜单 / 购物车 / 结算 / 成功全部手写。

| 表面 | 结构 | 金额字号 / 字重 | 色 | 路径 |
|---|---|---|---|---|
| 首页招牌 | `¥` + 金额 + 后缀 三 text | 40rpx / **900**（¥ 28rpx / 800） | `--brand` | `HomeTab.vue` L48–L51、L411–L420 |
| 菜单菜卡 | 同上三 text | 40rpx / **700**（¥ 24rpx / 700） | `--brand` | `DishList.vue` L94–L97、L606–L615 |
| PriceText md（未用） | 同结构 | 40rpx / 700（¥ 24rpx） | `--brand` | `PriceText.vue` L75–L77 |
| 购物车合计 | **单 text** `¥{{ formatPrice }}` | **48rpx** / 700 | `#fff`；脉冲时 `#34f38a` | `CartBar.vue` L15、L146–L157、L239–L241 |
| 结算已选合计 | 单 text | **34rpx** / 900 | `--brand` | `CheckoutSheet.vue` L30、L266 |
| 结算行价 | 单 text `currency + (price*qty).toFixed(2)` | **30rpx** / 900 | `--brand` | `CheckoutSheet.vue` L45、L293 |
| 结算应付 | 单 text | **52rpx** / 900 | `--brand` | `CheckoutSheet.vue` L89、L366–L369 |
| 成功实付 | `currency` + `toFixed(2)` | 先写 88rpx，sheet 覆盖成 **68rpx** / 900 | **`#111`**（不是 `--text-1` / `--brand`） | `PaymentSuccessSheet.vue` L10–L12、L223–L237、L404–L414 |
| 成功赠券 | `¥` + 金额 | 68rpx / 900 | `--text-inverse` 在券红底上 | `PaymentSuccessSheet.vue` L33–L35、L531–L547 |

格式函数也不统一：菜卡走 `dishPriceText()`（`useOrderFormatters.js`）；CartBar 走 `formatPrice`；CheckoutSheet 多处 **模板内** `toFixed(2)`；成功实付也是 `successTotal.toFixed(2)`。这不只是样式问题。

### SPEC_GAP

- `PriceText` 已存在且 md 档与菜单菜卡数字几乎同尺寸，首页/菜单仍手写。首页字重 900 vs PriceText 700。
- 成功实付 `#111` 未走 `--text-1`（`#111827`）。
- 购物车脉冲高亮 `#34f38a` 不是 `--brand` / `--success`。
- 结算行用拼接字符串，不走 `formatPrice` / PriceText。

### DECISION

- PriceText 只有 sm/md/lg，**覆盖不了** CartBar 白字 48rpx、结算应付 52rpx、成功实付 68/88rpx。把这些硬塞进现有三档会改语义，需要先决定：菜价、应付、实付、券面是否同一组件。
- 深色 CartBar 上的白字价格 vs 浅色页的品牌绿价格：是「同一 Price 家族的 inverse」还是「底栏专属数字」，未定。
- 成功页实付做成仪式大数字（接近黑、68–88rpx）还是继续品牌绿，未定。这是成功页信息层级决策。
- 券面红金字是 Constitution 允许的业务色，不要并进 `--brand`。

---

## 4. Spacing

**已有合同：** 无 spacing token。`DESIGN_SYSTEM_CURRENT.md` 已记录。Constitution Deferred。

本路径现场数字（不是规范，是观察）：

| 表面 | 页面/块 padding | 块间距 | 路径 |
|---|---|---|---|
| 首页 | `32rpx 32rpx`，底 `132rpx + safe` | 列 gap **28rpx** | `HomeTab.vue` L134–L141 |
| 菜单头 | `24rpx 32rpx 20rpx` | 内部 gap 20/12 | `ShopHeader.vue` L62–L67、L75 |
| 菜单菜卡 | 外边距 `0 20rpx 16rpx`，内边距 `20/20/20/24` | — | `DishList.vue` L444–L445 |
| 菜单分类栏 | 宽 168rpx；项高 108rpx | — | `DishList.vue` L273–L288 |
| 购物车条 | `12rpx 24rpx`；条高 148rpx + safe | 内部 gap 16rpx | `CartBar.vue` L62–L73 |
| 结算内容 | `20rpx 24rpx 18rpx`；底栏 `16rpx 24rpx` | 卡之间 18rpx | `CheckoutSheet.vue` L190–L196 |
| 成功 sheet | `18rpx 24rpx` + safe | 内卡 pad `44rpx 34rpx 28rpx` | `PaymentSuccessSheet.vue` L336–L344、L357–L362 |
| 底栏 | 高 `100rpx + safe` | — | `BottomNav.vue` L38–L44 |

左右边：首页 32、菜单卡 20、结算/成功 24，三条路径三个页边。底栏预留也不统一：HomeTab 底 pad `132rpx+safe`，DishList `.list-pad` `348rpx+safe`（给 CartBar + BottomNav）。

### SPEC_GAP

无 spacing token 可漏用。硬编码灰底接近 token 的，算颜色不是间距：分类栏 `#F6F7F8` 等于 `--bg-subtle` 却手写（`DishList.vue` L276）。

### DECISION

- 页边 20 vs 24 vs 32、块间距 16 vs 18 vs 28，要不要倍数表，属于 typography/spacing Deferred。
- CartBar（148rpx）叠在 BottomNav（100rpx）上，菜单必须自己垫 `.list-pad`。这是布局合同，不是 spacing token 能单独解决的。未来若统一底栏高度，要连安全区一起定。

---

## 5. Typography

**已有合同：** 无字号/字重 token。`--text-1/2/3` 是颜色不是 type scale。Constitution Deferred。

本路径标题/正文抽样：

| 角色 | 字号 / 字重 / 色 | 路径 |
|---|---|---|
| 首页店名 | 40rpx / 700 / `--text-1` | `HomeTab.vue` L163–L172 |
| 菜单头店名 | **34rpx** / 700 / `--text-1` | `ShopHeader.vue` L115–L125 |
| 首页 Hero 标题 | 48rpx / 800 / `#2b1c0f`（棕色，不是 text token） | `HomeTab.vue` L237–L244 |
| 首页 section 标题 | 34rpx / 800 / `--text-1` | `HomeTab.vue` L297–L304 |
| 菜单菜名 | 32rpx / **600** / `--text-1` | `DishList.vue` L583 |
| 首页招牌菜名 | 36rpx / **800** / `--text-1` | `HomeTab.vue` L370–L380 |
| 结算弹层标题 | 36rpx / **900** / `--text-1` | `CheckoutSheet.vue` L185 |
| 成功标题 | 46rpx / 900 / `--text-1`（覆盖更早的 40rpx） | `PaymentSuccessSheet.vue` L389–L395 |
| 说明/辅文 | 24–28rpx / `--text-3` 或硬编码灰 | 各文件 |
| 菜单分类名 | 24rpx / 600；active 800 / `--brand` | `DishList.vue` L323–L348 |
| 结算行名 | 31rpx / 800 | `CheckoutSheet.vue` L284 |
| 成功摘要值 | 29rpx / 800 / `--text-1` | `PaymentSuccessSheet.vue` L641–L650 |

同一「店名」在首页 40rpx、菜单头 34rpx。同一「菜名」在首页招牌 36/800、菜单列表 32/600。标题字重 700/800/900 混用。

硬编码字色（有 token 可走）：

- 首页 Hero 文案 `#2b1c0f` / `rgba(58,38,18,0.75)`：叠在品牌背景图上，`--text-inverse` 并不合适（DECISION，见下）。
- 菜单分类未选 `#6F7680` / `#9CA3AF`（`DishList.vue` L297、L316、L328），接近 `--text-3` `#6b7280`。
- 月售 `#A8ADB4`（`DishList.vue` L600），比 `--text-3` 更浅。
- ShopHeader 打烊 `#999`（L139），未走 `--text-3`。
- 结算会员文案 `#475467` / `#1d4f91`（`CheckoutSheet.vue` L225–L233），会员蓝不是 token。
- 成功次按钮字 `#344054`（`PaymentSuccessSheet.vue` L689）。

### SPEC_GAP

- 分类灰、打烊灰、月售灰、成功次按钮字，都可以落到 `--text-2/3` 却手写。这是已有颜色 token 缺失，不是缺 type scale。
- ShopHeader `color: var(--text-1, #1a1a1a)` 的 fallback 是 `--ink` 的值，不是 `--text-1`。

### DECISION

- 没有 title/body/caption 档，不能把 31rpx vs 32rpx vs 34rpx 判成「违例」。
- 首页 Hero 用深棕压在绿图上，是这张背景图的对比度选择，不能改成 `--text-inverse` 白字除非换图或加遮罩。
- 菜名 600 vs 招牌 800：列表密度 vs 推荐强调，未定是否允许两档。
- 结算/成功标题 900 是否作为「弹层标题合同」，未定。BaseSheet 标题是 36rpx/800（本路径未用 BaseSheet）。

---

## 6. State 展示

**已有合同：**

- 新页级 loading / empty / error 必须用 `StateLoading` / `StateEmpty` / `StateError`（Constitution「Page-level State」）。
- 菜单骨架 `LoadingStates` **是合法独立 primitive**，不要并进 StateError（Deferred：合并 LoadingStates）。
- 券红、会员金允许。

本路径实际：

| 状态 | 当前实现 | 是否 State* | 路径 |
|---|---|---|---|
| 菜单加载 | 骨架屏 | 否（合法 LoadingStates） | `LoadingStates.vue` L7–L21、L56–L69；`menu.vue` L419–L423 |
| 菜单加载失败 | 白遮罩 + 文案「菜单加载中...」+ 重试 | **否**；且文案把 error 写成 loading | `LoadingStates.vue` L2–L4、L39–L49 |
| 菜单空 | PNG + 「暂无菜品」+ 重试 | 否，未用 StateEmpty | `DishList.vue` L48–L53、L660–L706 |
| 菜品售罄 | 缩略图遮罩「已售罄」+ 灰胶囊按钮 | 无对应 primitive | `DishList.vue` L75、L490–L492、L648–L651 |
| 店铺打烊（首页） | 胶囊「休息中」`#F1F3F5` / `--text-3` | 无 | `HomeTab.vue` L8–L10、L201–L203（L126–L129 是被覆盖的旧色） |
| 店铺打烊（菜单头） | 方标签「已打烊」`#999` / `#f0f2f5`，圆角 8rpx | 无 | `ShopHeader.vue` L11–L13、L127–L141 |
| 购物车空 | 深底栏「未选择商品」+ disabled CTA | 无 | `CartBar.vue` L18–L19、L170–L179、L199–L202 |
| 结算不可提交 | 主按钮变 `#cbd5e1` | 无 | `CheckoutSheet.vue` L95、L375 |
| 结算无桌台 | 桌台卡改橙底 | 无 | `CheckoutSheet.vue` L10、L199 |
| 支付成功进行中 | `.order-status-bar` 绿底文案 | 无 | `PaymentSuccessSheet.vue` L16–L18、L427–L462 |
| 规格层 | 用 PriceText + AddBtn | 部分 | `SpecSheet.vue` |

`HomeTab.vue` L121–L129 与 L187–L203 **两套** `.ht-status-badge*`。后写的生效（开业 `#E8F8EF`/`#087A3D`，打烊灰）。前一套（绿 `#d1fae5`/`#065f46`、红 `#fee2e2`/`#991b1b`）是死代码。

开业态也和菜单头不一致：首页胶囊 999rpx + `#087A3D`，菜单头圆角 8rpx + `#06ad56`。`#087A3D` / `#06ad56` 都不是 `--brand-dark` `#059952`。

### SPEC_GAP

- 菜单空态应走已有 `StateEmpty`（页级 empty）。现在是 PNG 私有空态，标题 34rpx/800 vs StateEmpty 30rpx/600。
- 菜单失败态应走已有 `StateError`。`LoadingStates` 在 `loadError && !loading` 时仍显示「菜单加载中...」（`LoadingStates.vue` L2–L3），反馈错误。
- 首页/菜单头开业·打烊色未走 `--brand` / `--brand-light` / `--text-3`。
- `.tap-shrink` 在 State* 按钮上有，LoadingStates / DishList 重试按钮没有。

### DECISION

- LoadingStates 骨架屏按 Constitution **保持独立**。要不要视觉上向菜卡看齐（骨架 thumb 20rpx vs 菜卡 `--radius-card`）是细节，不是强制迁移。
- 售罄、打烊、购物车空、结算 disabled 是 **控件级** 状态，没有 State* 变体，不能塞进页级 Empty/Error。未来要不要做统一 badge / disabled token，未定。
- 成功页订单状态条（绿底进行中 / 橙警告）是业务状态，不是页级 State*。色板（`#ecfbf3` / `#fff7ed`）与结算桌台卡重复，但是否抽「tone chip」未定。
- 空菜单用插画 PNG vs StateEmpty 默认 emoji：Constitution 已承认没有统一空态插画。换成 StateEmpty 会丢插画，需要设计决定。

---

## 7. 页面层级

分两层：**(A) z-index 合同**（Constitution 可执行）；**(B) 视觉信息层级**（谁是第一眼）。

### 7A. z-index / Overlay

已有 layer token：`--z-chrome 300` / `--z-floating 850` / `--z-blocking 3100` / `--z-blocking-top 3200` / `--z-critical 4000`。

本路径实际：

| 表面 | 实际 z | 是否 token | 路径 |
|---|---|---|---|
| BottomNav | **300** 字面量 | 值等于 `--z-chrome`，未写 token | `BottomNav.vue` L49 |
| CouponBar 催用条 | **319** 发明 | 否 | `CouponBar.vue` L144 |
| CartBar | **320** 发明 | 否 | `CartBar.vue` L64 |
| OrderBubble | **850** 字面量 | 值等于 `--z-floating`，未写 token | `order-bubble.vue` L275；hint L393 = **851** |
| LoadingStates | **2000** 发明 | 否；落在 floating 与 blocking 之间的无名带 | `LoadingStates.vue` L42 |
| Checkout / Success / Spec / CouponPicker | `--z-blocking` via `.mask` | ✓ 遗产允许 | `_shared.scss` L11–L14；各 sheet `@import _shared.scss` |
| CheckoutAuth / MemberCheckoutChoice | BaseOverlay `blocking-top` 3200 | ✓ | Constitution 已登记 |

`menu.vue` DOM 顺序（L199–L423）把 CheckoutSheet 放在 Auth/Choice/Success 前面。Constitution 写明 **DOM 不是叠层权威**，3200 > 3100 才是。结构合同这一条是满足的。

CheckoutSheet / PaymentSuccessSheet / SpecSheet 仍走 `.mask`，未迁 BaseSheet。这是已知 TOUCH_AND_MIGRATE 债，不是本阶段要修的视觉问题。CI allowlist 仍登记这些路径（`base-sheet.contract.test.js` 点名 CheckoutSheet、PaymentSuccessSheet）。

成功遮罩色：`.success-mask` 先写 `rgba(10,16,30,0.75)`（L132–L137），后覆盖为 `rgba(15,23,42,.52)`（L326–L332）。两者都 **不是** `--overlay-dim` `rgba(0,0,0,0.5)`。`.mask` 本身用 `--overlay-dim`，成功页又改掉。

### 7B. 视觉信息层级（五步里「第一眼」是什么）

| 步骤 | 第一眼 | 第二眼 | 问题 |
|---|---|---|---|
| 首页 | 绿 Hero「立即点餐」 | 店名状态卡、招牌菜 | Hero 反相按钮 vs 后续绿底白字，跨步不连续 |
| 菜单 | 左分类 + 菜卡价 + 加号 | 顶店头、券条、底深色 CartBar | 底栏突然切到深色 `#1f2937` / `--text-1`，与浅色首页/菜单列表不是同一套 chrome |
| 购物车 | 白字大价 + 绿胶囊「去结算」 | 份数 | 价格是路径上最大的白字（48rpx），比菜卡绿价更抢 |
| 结算 | 应付 52rpx 绿字 + 104rpx 方按钮 | 桌台绿卡、菜品折叠行 | 主按钮比 CartBar 更高、更方、字更重（900 vs 600） |
| 成功 | 勾 + 68rpx 黑字实付 | 状态条、券红卡、三按钮 | 实付改黑色，主按钮又变 `--radius-card`；文件内还有一套居中 modal 旧样式未删 |

Chrome 叠层（菜单 Tab）：ShopHeader → CouponBar → 列表 → CartBar（深）→ BottomNav（白）。用户在同一屏看到浅顶 + 深车 + 白 Tab，三截。

### SPEC_GAP

- BottomNav / OrderBubble 应用 `--z-chrome` / `--z-floating`，现在写死同值。
- CartBar 320、CouponBar 319、LoadingStates 2000 **发明了未命名层级**。Constitution 禁止发明 blocking 段数字（3000/3100/9000/9999）；2000 不在点名黑名单里，但也不在五档 token 内，属于「无名带」。
- 成功页遮罩未保持 `--overlay-dim`。
- Checkout / Success 未走 BaseSheet（已知 overlay 采用缺口，见 `DESIGN_SYSTEM_ADOPTION_AUDIT.md`）。本路径视觉后果：sheet 顶角/标题/关闭按钮与已迁的 OrderHistory 不一致。

### DECISION

- CartBar 深色底是否保留。这是整条高频路径最大的「家族分裂」：列表浅、车深、Tab 白、结算浅。没有 token 能表达「chrome 允许深色反相」。要先决定 CartBar 是（1）继续深色强调条，还是（2）改成浅色底栏与结算 sheet 一家。
- CouponBar 催用条 319 vs CartBar 320：要贴在车上方（现在这样）还是改 floating。数值本身是为了塞进 300 与车之间，不是设计系统。
- LoadingStates 2000：骨架要盖住列表但仍低于 blocking sheet。现有五档没有「content overlay」。塞进 `--z-floating`（850）会和 OrderBubble 抢；升到 blocking 会盖住不应盖的。需要层合同扩展决策，**禁止本阶段发明新 z token**。
- 成功页要底栏 sheet 还是居中卡：源码两套样式说明历史改过一次，只留了后写的底栏。旧规则（L132–L321 前半）仍在文件里，后续改按钮容易改错套。清理死 CSS 是工程债，不是新视觉规范。

---

## 8. 跨项对照（同一元素，五步各写一套）

只列「同一用户目标、五种写法」。方便后续阶段挑 TOUCH 面，不在本阶段改。

### 8.1 主 CTA（去点餐 / 去结算 / 支付 / 完成）

60rpx 胶囊（菜单选规格）→ 92rpx 胶囊（车）→ 104rpx 方（结算）→ 98rpx `--radius-card`（成功）→ 100rpx 胶囊 token（规格，本路径侧翼）。字重 600→900。

**SPEC_GAP：** 不走 `--btn-primary-*`。  
**DECISION：** 哪一档才是主 CTA；深色条上的胶囊 vs 浅色 sheet 上的方按钮是否允许并存。

### 8.2 金额

菜卡绿 40/700 → 车白 48/700 → 结算应付绿 52/900 → 成功黑 68/900。

**SPEC_GAP：** 不走 `PriceText`；成功 `#111` 不走 `--text-1`。  
**DECISION：** 应付/实付要不要比菜价大一档；深色反相价是否新档。

### 8.3 营业状态

首页胶囊 999rpx `#087A3D` vs 菜单头 8rpx `#06ad56`；打烊灰两套。死代码还留着第三套红绿。

**SPEC_GAP：** 不用 `--brand` / `--brand-light`。  
**DECISION：** 状态 badge 形状（胶囊 vs 小方）未定，无 primitive。

### 8.4 空 / 错

StateEmpty/Error 已有且会员/券页在用；点餐主路径 PNG + LoadingStates 文案错误。

**SPEC_GAP：** 页级 empty/error 合同未采用。  
**DECISION：** 插画是否保留。

---

## 9. 已对齐、不要当缺口重做

避免下一阶段「为了统一而改已经对的东西」。

1. 品牌绿主填充已经是 `var(--brand)`：HomeTab 加入/Hero 底、DishList 加号/选规格、CartBar CTA、Checkout 提交、Success 主按钮、SpecSheet 确认。没有本路径上的 `#16c76f` / 会员页那种残留 `#07C160`（那些在 `pages/index`、`payment-handoff`、`verify-qr`，**范围外**）。
2. 菜卡是本路径唯一完整采用 `--radius-card` + `--card-shadow` 的列表卡（`DishList.vue` L448–L449）。
3. 结算内容卡已用 `--radius-card`（`CheckoutSheet.vue` L196/L245）。
4. 成功主/次按钮已用 `--radius-card`（`PaymentSuccessSheet.vue` L664/L681）。
5. Overlay 叠层：结算 3100、鉴权/入会 3200，符合 Constitution。
6. 券红金（成功赠券卡）按 Constitution 允许，不要并进 brand。
7. LoadingStates 骨架作为菜单加载 primitive 是合法的，不要本阶段改造成 StateLoading 圆环。
8. 点击加购回弹 `--bounce-ease` 在 DishList 选规格/加号上有用（`DishList.vue` L710、L721）。

---

## 10. 后续阶段建议（不是本阶段任务）

只排序，不实施。每一项仍须 TOUCH_AND_MIGRATE，禁止 BIG_BANG。

**可在不新增 token/组件的前提下修（纯采用）：**

1. 菜单空/错接到现有 StateEmpty / StateError；顺手改掉 LoadingStates 失败文案「菜单加载中...」。
2. 菜卡价格改为 `PriceText` size=md（与现状 24/40/22 对齐，首页招牌要先决定要不要 900）。
3. 加号改为 `AddBtn`（会从 60rpx 变成 72rpx，有视觉跳动，需产品点头——若不可接受则归 DECISION）。
4. BottomNav / OrderBubble 的 300/850 改写成 `var(--z-chrome)` / `var(--z-floating)`（像素不变）。
5. 成功实付 `#111` → `var(--text-1)`；分类/打烊灰能映射的改 `--text-3`。
6. 删掉 HomeTab 失效的第一套 badge、PaymentSuccessSheet 失效的居中 modal 规则，降低后续误改。

**必须先设计决策再动：**

1. 主 CTA 家族：高度、圆角、字重；CartBar 胶囊 vs Checkout 方按钮。
2. CartBar 深色是否留。这是路径级视觉家族问题。
3. Price 在「菜价 / 底栏合计 / 应付 / 实付」是否同一组件，要不要扩档（扩档 = 新 API，接近新规范，需单独阶段）。
4. LoadingStates 的 2000 放进哪一档 layer；禁止顺手加第六个 z token。
5. Checkout / Success 迁 BaseSheet：这是 overlay 债，会改顶角/标题/关闭，需单独 overlay 阶段，不是「统一按钮」能捎上的。
6. AppButton / AppCard / type / spacing scale：Constitution Deferred，本系列在决策前禁止创建。

---

## 11. 本阶段没做

- 没有改任何 `.vue` / `.scss` / token。
- 没有创建 AppButton、AppCard、新 State 变体。
- 没有新增 Design Token。
- 没有把 Deferred 写成现行规范。
- 没有审会员 Tab、我的、进店页、本桌订单。
- 没有在真机/模拟器上目测（只读源码）。视觉「看起来裂」的判断来自数值差，不是截图。
