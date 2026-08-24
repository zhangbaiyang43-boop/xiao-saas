# 开心点单 — 当前设计系统审计（DESIGN_SYSTEM_CURRENT）

```
MODE=READ_ONLY_REVERSE_AUDIT
DATE=2026-08-24
SCOPE=member-mini-client + admin-h5
CODE_CHANGE=NO
```

本文只记录仓库里已经形成的 UI 规则。数值全部来自现有源码。没有独立的 `app.wxss` / `theme.json` / Figma token 文件。不把外部设计规范写进来，也不把「应当长什么样」写成新规范。

对照关系：

| 文档 | 职责 |
|---|---|
| `member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md` | 前端结构合同（Overlay / BaseSheet / layer / CI）。不是视觉目录。 |
| 本文 | 从代码反推的视觉语言、token、组件采用现状、不一致点。 |

---

# 一、当前已有设计语言

## 1.1 实际品牌色

两端主品牌色已经对齐到微信绿：

| 位置 | 实际值 |
|---|---|
| 小程序 `src/styles/global.scss` `--brand` | `#07C160` |
| 商家后台 `admin-h5/src/styles/global.scss` `--brand` | `#07C160` |
| 商家后台 Ant Design `App.vue` `colorPrimary` | `#07C160` |
| 点餐页 / 付款页微信导航栏 | `#07C160` + 白字 |

第三条绿 `#16c76f` 已在 P1-DESIGN-TOKEN-CONSOLIDATION-PHASE-02 从业务样式移除（entry 主按钮/loading 环、MemberCheckoutChoice、CheckoutAuthSheet 改为 `var(--brand)`）。Constitution 仍禁止再引入该值。

## 1.2 两端视觉家族

**顾客端（uni-app / mp-weixin）**

- 页面底 `#f5f6fa`，卡片白底，圆角偏大（24–36rpx，弹层顶部 32–40rpx）。
- 点餐主路径是深色底栏（CartBar `#1f2937`）+ 绿色 CTA，不是浅色底栏。
- 字体层级没有 token，靠 `font-size: 22–40rpx` 和 `font-weight: 600/700/800/900` 现场写。
- 弹层：一部分已走 BaseOverlay / BaseSheet；结账 / 规格 / 优惠券仍走 `_shared.scss` 的 `.mask`。
- Toast / Modal 没有自研组件，全部 `uni.showToast` / `uni.showModal`。
- `@vant/weapp` 在 `pages.json` 的首页注册了 button/cell/grid/tag/empty/popup，**业务 `.vue` 模板里零使用**。

**商家端（admin-h5 / H5）**

- 主框架是 Ant Design Vue 4。`a-config-provider` 把主色钉成 `#07C160`，圆角 token 是 **8px**。
- 自研 CSS token 里卡片圆角是 **12px**，Hero 底部圆角 **28px**。三套圆角同时存在。
- 今日页用 `.hero-header` 绿渐变头 + `StatCard`；订单 / 菜品管理用页面内联 `.page-header`；设置 / 会员列表用 `PageHeader`。三种顶栏。
- `vant` 4 仍在 Dashboard 下拉刷新、扫码、部分自定义控件里。
- `admin-h5/src/styles/variables.scss` 仍是 indigo（`#6366f1`）。Vite 全局注入。`DataCard.vue` 还在用这套色，但 **没有任何页面引用 DataCard**。
- `ListState.vue` 写了 `el-empty` / `el-button`，`package.json` 没有 `element-plus`，且没有任何 view 引用它。

## 1.3 已经形成、并且被多处遵守的规则

1. 品牌绿以 `--brand: #07C160` 为权威名字（新点餐组件多数已经 `var(--brand)`）。
2. 文本三档 `--text-1 / --text-2 / --text-3` 在点餐子包里使用密度最高。
3. Overlay 几何 / 遮罩 / z-index 归 BaseOverlay；新标准底栏弹层归 BaseSheet。这是结构合同，不是视觉统一已经完成。
4. 点击反馈有公共类 `.tap-shrink`（scale 0.96 / 0.15s），两端同名。
5. 优惠券允许独立红金配色（`#ff5a3c` → `#d81717`），不并进品牌绿。
6. 会员卡允许等级专属文字色（`--member-text-primary/secondary/tertiary`），只活在 MemberCard。

## 1.4 明确还不存在的系统

源码中没有：

- spacing token（小程序零档位；商家 SCSS 有 `$spacing-xs…xl` 但页面几乎不用）
- typography token（没有 `--font-title` / `--font-body`）
- 完整 radius 档位（只有 `--radius-card` / `--radius-hero`）
- AppButton / AppCard / AppTag / AppToast
- 统一空状态插画（StateEmpty 默认 emoji；菜单空态用 PNG；本桌订单空态用灰圆）

Constitution Deferred 已点名：AppButton、AppCard、typography/spacing/radius、全量 hex 清理。本文确认这些确实还没落地。

---

# 二、Design Token

## 2.1 颜色 — 实际值

### 小程序 `member-mini-client/src/styles/global.scss`（挂在 `page {}`）

| Token | 实际值 | 源码中 `var(--*)` 出现次数（业务 src，不含测试/npm） |
|---|---|---|
| `--brand` | `#07C160` | 93 |
| `--brand-dark` | `#059952` | 1 |
| `--brand-light` | `#e8f9f0` | 6 |
| `--brand-gradient` | `linear-gradient(135deg, #07C160 0%, #10A85A 100%)` | 3 |
| `--text-1` | `#111827` | 60 |
| `--text-2` | `#4b5563` | 19 |
| `--text-3` | `#6b7280` | 81 |
| `--text-inverse` | `#fff` | 31 |
| `--ink` | `#1a1a1a` | 1 |
| `--bg-page` | `#f5f6fa` | 7 |
| `--bg-card` | `#ffffff` | 21 |
| `--bg-muted` | `#f3f4f6` | 4 |
| `--bg-subtle` | `#f6f7f8` | 4 |
| `--border` | `#f0f0f0` | 7 |
| `--success` | `#059952` | 定义了，业务使用接近 0（成功色多数直接用 brand） |
| `--danger` | `#ef4444` | 5 |
| `--warning` | `#f59e0b` | 4 |
| `--overlay-dim` | `rgba(0,0,0,0.5)` | 2（定义处 + `_shared.scss` `.mask`） |
| `--z-chrome` | `300` | BottomNav 写死 `z-index: 300`，未走 token |
| `--z-floating` | `850` | 定义了，业务几乎不读 |
| `--z-blocking` | `3100` | BaseOverlay + `.mask` |
| `--z-blocking-top` | `3200` | BaseOverlay |
| `--z-critical` | `4000` | BaseOverlay |

硬编码 hex 仍多于 token。出现最多的非 token 色（业务 src 粗计）：

| 硬编码 | 次数量级 | 典型去向 |
|---|---|---|
| `#fff` | 134 | 按钮字、卡片 |
| `#07c160` / `#07C160` | 50 | 会员子包、券详情、核销页、部分未改 token 的页面 |
| `#111827` | 27 | 本可走 `--text-1` |
| `#999` | 20 | 旧灰 |
| `#f7f8fa` / `#f5f7fb` / `#edf0f2` | 10–15 | 接近 `--bg-page` / `--border` 的变体 |
| `#9ca3af` | 会员/券等页 | 浅灰；`--text-3` 已加深到 `#6b7280`。StateEmpty 已改用 `--text-3` |
| `#16c76f` | 0 in live styles | PHASE-02 已改为 `--brand`；Constitution 仍禁止再引入 |
| `#ff5a3c` / `#ff2f1f` / `#d81717` | 券面红 | 优惠券业务色 |
| `#F04444` | CartBar badge | 接近但不是 `--danger` |
| `#4B5362` | CartBar 空车按钮 | 无 token |

会员卡局部 token（只在 `MemberCard.vue` / `useMemberCard.js`）：

| 等级 | `--member-text-primary` | `--member-text-secondary` | `--member-text-tertiary` |
|---|---|---|---|
| LV1 默认 | `#123B2A` | `#35634F` | `#527563` |
| LV2 | `#26323A` | `#53616B` | `#6F7B83` |
| LV3 | `#4A3210` | `#715224` | `#8A6A37` |

### 商家后台 `admin-h5/src/styles/global.scss`（挂在 `:root`）

| Token | 实际值 | 小程序有没有同名 |
|---|---|---|
| `--brand` | `#07C160` | 有，同值 |
| `--brand-dark` | `#059952` | 有，同值 |
| `--brand-light` | `#e8f9f0` | 有，同值 |
| `--brand-mid` | `#9de8c4` | 小程序无 |
| `--text-1/2/3` | `#111827` / `#4b5563` / `#6b7280` | 有，同值 |
| `--bg-page` | `#f5f6fa` | 有，同值 |
| `--bg-card` | `#ffffff` | 有，同值 |
| `--border` | `#f0f0f0` | 有，同值 |
| `--radius-card` | `12px` | 小程序是 `24rpx`（750 稿约等于 12px） |
| `--success` | `#059952` | 有 |
| `--danger` | `#ef4444` | 有 |
| `--warning` | `#f59e0b` | 有 |
| `--hero-bg` | `linear-gradient(135deg, #06d16e 0%, #07C160 45%, #048a49 100%)` | 小程序无此 token（小程序 `--brand-gradient` 不同） |
| `--hero-dark` | `#1a1a2e` | 无 |
| `--card-shadow` | `0 4px 20px rgba(17,24,39,.05)` | 小程序是 `0 4rpx 16rpx rgba(17,24,39,0.06)` |
| `--gold` / `--silver` / `--bronze` | 等级渐变 | 小程序无 |
| `--card-border` | `transparent`（暗色 `#262931`） | 无 |

商家后台另有暗色：只翻转 token，不改组件代码。小程序 **没有** 对应暗色。

### 商家后台遗留 SCSS 变量 `variables.scss`（Vite `additionalData` 全局注入）

| 变量 | 实际值 | 现状 |
|---|---|---|
| `$color-primary` / `$primary-main` | `#6366f1` | 与线上绿品牌冲突 |
| `$primary-color` | `linear-gradient(135deg, #6366f1, #8b5cf6)` | `DataCard.vue` 使用，DataCard 无页面引用 |
| `$spacing-xs…xl` | 4 / 8 / 12 / 16 / 24 px | 几乎不被页面采用 |
| `$card-radius` | `12px` | 与 `--radius-card` 同值不同通道 |
| `$tabbar-height` | `56px` | 与 `.bottom-tabbar` 高度一致 |
| `$navbar-height` | `44px` | 实际 `PageHeader` / `.navbar` 高度是 52px |

## 2.2 字体 — 实际值

**家族**

- 小程序 `page`：`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`
- 商家 Ant token：同一系统栈，无 Helvetica Neue

**没有字号 token。** 小程序 `font-size` 出现次数（业务样式）：

| 实际值 | 次数 | 经验角色（观察，不是规范） |
|---|---|---|
| 24rpx | 80 | 辅助、标签、状态 |
| 26rpx | 74 | 说明、次要正文 |
| 28rpx | 58 | 关闭图标、部分正文 |
| 30rpx | 58 | 按钮、空状态标题 |
| 22rpx | 40 | 更小辅助 |
| 32rpx | 33 | 主按钮字（`--btn-primary-font-size` 也是 32rpx） |
| 34rpx | 31 | 结算按钮、部分标题 |
| 36rpx | 23 | BaseSheet / CheckoutSheet 标题 |
| 40rpx | 23 | SpecSheet 菜名、金额 |
| 48rpx | 6 | CartBar 价格 |
| 72rpx | 6 | StateHeroStat 大数字、空态 emoji |

**字重（小程序）**

| 实际值 | 次数 |
|---|---|
| 700 | 74 |
| 900 | 65 |
| 600 | 60 |
| 800 | 57 |
| bold | 17 |
| 400 | 10 |
| 500 | 7 |

标题经常 900，按钮经常 600/800/900 混用。没有「标题 / 正文 / 按钮」字重合同。

**商家后台常见字号（观察）**

- Hero 店名 22px / 900
- Section 标题 12px / 600 / uppercase
- PageHeader 标题 17px / 700 / `#111`（不用 `--text-1`）
- TabBar 10px
- 统计数字 22–38px / 900 / tabular-nums
- Ant Tag 强制 12px

## 2.3 Spacing — 实际值

小程序 **没有 spacing token**。页面和组件直接写 rpx。高频是 12 / 16 / 20 / 24 / 28 / 32 / 36 / 48 rpx，没有统一倍数表。

已命名的尺寸 token 只有按钮：

| Token | 实际值 | 出处 |
|---|---|---|
| `--btn-primary-height` | `100rpx` | SpecSheet 确认按钮回溯 |
| `--btn-primary-radius` | `50rpx` | 同上 |
| `--btn-primary-font-size` | `32rpx` | 同上 |
| `--btn-primary-font-weight` | `600` | 同上 |

`--page-pad` 在 token 计数里出现 1 次，**global.scss 未定义该名**。

商家后台 SCSS 有 4/8/12/16/24px 档，但今日页 / 接单页实际用的是：

- `.page-body` 12px 16px 0
- `.section-block` 14px 16px 0
- `.info-row` 13px 16px
- 大量内联 `padding: 0 16px`

安全区：两端都用 `env(safe-area-inset-bottom)`。小程序底栏高度 `100rpx + safe-area`；商家 TabBar `56px + safe-area`。

## 2.4 Radius — 实际值

| Token / 写法 | 实际值 | 用途 |
|---|---|---|
| `--radius-card`（小程序） | `24rpx` | 部分卡片、结算次按钮 |
| `--radius-hero`（小程序） | `36rpx` | 我的页卡片 |
| `--radius-card`（商家） | `12px` | Ant Card override |
| Ant `borderRadius` | `8px` | 全局 Ant 控件 |
| `.hero-header` | `0 0 28px 28px` | 今日页头 |
| BaseSheet / CheckoutSheet / CouponPicker / MemberChoice | `32rpx 32rpx 0 0` | 底栏弹层 |
| SpecSheet | `40rpx 40rpx 0 0` | 规格弹层，比其它弹层更大 |
| 胶囊 | `999rpx` / `999px` | chip、badge、部分主按钮 |
| 圆形 | `50%` | 加号、关闭、头像 |
| 硬编码高频 | `20rpx`（36 次） | 菜卡、reorder 条，**比 `--radius-card` 更常用** |

## 2.5 Shadow / 动效 — 实际值

| Token / 类 | 实际值 |
|---|---|
| `--card-shadow`（小程序） | `0 4rpx 16rpx rgba(17,24,39,0.06)` |
| `.card-base` | 白底 + `--radius-card` + `--card-shadow`。**没有任何页面使用这个类。** |
| `--card-shadow`（商家） | `0 4px 20px rgba(17,24,39,.05)` |
| CartBar | `0 -6rpx 20rpx rgba(0,0,0,0.18)` |
| 主 CTA 绿光 | `0 8rpx 24rpx rgba(7,193,96,0.35)` 或 `0 14–16rpx 32–34rpx rgba(16,196,105,.22)` |
| `--bounce-ease` | `cubic-bezier(0.34, 1.56, 0.64, 1)` |
| `.tap-shrink` | transform 0.15s + active `scale(0.96)` / opacity 0.85 |
| `@keyframes bounceIn` | 加购回弹，定义在 global |
| `@keyframes slide-up` | `_shared.scss`，CouponPicker / SpecSheet |
| `@keyframes cartQtyPulse` | 数量变化 |
| `@keyframes memberChoiceIn` | MemberCheckoutChoice 单独 0.2s |
| BaseSheet | **没有入场动画** |
| 商家 `.animate-in` | `fadeSlideUp` 0.42s |
| 商家 `.live-dot` | 1.6s 呼吸点 |
| `prefers-reduced-motion` | `_shared.scss` 关掉 counter / cart / checkout 动效 |

---

# 三、组件规范

「使用次数」= **引用它的业务文件数**，不含自身、不含测试。次数为 1 表示只被 `menu.vue` 或单个页面用。

## 3.1 顾客端 — 已是事实标准的原语

| 组件 | 文件 | 引用文件数 | 当前样式规则（源码） |
|---|---|---|---|
| BaseOverlay | `member-mini-client/src/components/base-overlay/base-overlay.vue` | 3（BaseSheet、MemberCheckoutChoice、CheckoutAuthSheet） | `position:fixed; inset:0`；backdrop `--overlay-dim`；layer → z-index 3100/3200/4000；非法 layer 不渲染 |
| BaseSheet | `member-mini-client/src/components/base-sheet/base-sheet.vue` | 2（OrderHistorySheet、TableBillSheet） | 组合 BaseOverlay；底栏白底；顶圆角 32rpx；max-height 86vh；标题 36rpx/800/`--text-1`；关闭 56rpx 圆、`#f3f4f6`；padding-bottom `24rpx + safe-area`；无入场动画 |
| StateLoading | `src/components/state-loading/state-loading.vue` | 11（我的、会员子包、券列表/详情） | 绿环 `#07C160` + `#d1fae5`，**不用 token**；标题 30rpx/700/`#111827` |
| StateError | `src/components/state-error/state-error.vue` | 11 | 标题 `#111827` 30rpx/700；按钮 88rpx、圆角 24rpx、底 `#07C160`（硬编码） |
| StateEmpty | `src/components/state-empty/state-empty.vue` | 7 | 默认 emoji；标题 `#333` 30rpx/600；说明 `#9ca3af` 26rpx；按钮同 StateError |
| StateHeroStat | `src/components/state-hero-stat/state-hero-stat.vue` | 1（points.vue） | 白字 72rpx/900，用在绿头里 |
| AddBtn | `src/subpkg-order/components/AddBtn.vue` | 1（SpecSheet） | `--brand` 圆；md 72rpx / sm 52rpx。菜卡加减仍用 `_shared.scss` `.counter-btn` |
| PriceText | `src/subpkg-order/components/PriceText.vue` | 1（SpecSheet） | `--brand`；sm/md/lg 三档。DishList / HomeTab / CartBar **自己写价格样式** |
| OrderBubble | `src/components/order-bubble/order-bubble.vue` | 2（menu、mine） | 点餐态浮层，z 带 chrome |

## 3.2 顾客端 — 点餐业务组件（单页事实标准，不是跨页 primitive）

全部由 `subpkg-order/pages/menu.vue` 组装，引用文件数均为 1。它们构成顾客主路径 UI，但没有抽成跨包组件。

| 组件 | 文件 | 当前样式要点 |
|---|---|---|
| HomeTab | `.../HomeTab.vue` | 首页内容；绿头 `--brand` + 背景图 |
| DishList | `.../DishList.vue` | 分类 + 菜卡；菜卡圆角 20rpx；空菜单用 PNG，不用 StateEmpty |
| ShopHeader | `.../ShopHeader.vue` | 门店头 |
| CartBar | `.../CartBar.vue` | 固定底 `z-index:320`；空态 `#1f2937`，有商品 `--text-1`；CTA 92rpx / 圆角 46rpx |
| BottomNav | `.../BottomNav.vue` | 四 Tab 图标无文字；高 `100rpx+safe`；`z-index:300`；active `--brand` |
| CouponBar | `.../CouponBar.vue` | 券条 |
| MemberCard | `.../MemberCard.vue` | 会员 Tab；等级文字 token |
| LoadingStates | `.../LoadingStates.vue` | 菜单骨架，与 StateLoading 并存 |
| CheckoutSheet | `.../CheckoutSheet.vue` | `.mask` 遗产；顶圆角 32rpx；底 `#f5f7f8`；标题 36rpx/900；主按钮 104rpx / 圆角 28rpx |
| SpecSheet | `.../SpecSheet.vue` | `.mask`；顶圆角 **40rpx**；max-height 90vh；确认按钮走 `--btn-primary-*` |
| CouponPicker | `.../CouponPicker.vue` | `.mask`；顶圆角 32rpx；`slide-up` 0.25s |
| OrderHistorySheet | `.../OrderHistorySheet.vue` | 已迁 BaseSheet |
| TableBillSheet | `.../TableBillSheet.vue` | 已迁 BaseSheet |
| PaymentSuccessSheet | `.../PaymentSuccessSheet.vue` | `.mask` 遗产 |
| WelcomeCouponSheet | `.../WelcomeCouponSheet.vue` | `.mask` 遗产 |
| MemberCheckoutChoice | `.../MemberCheckoutChoice.vue` | BaseOverlay `blocking-top`；顶圆角 32rpx；主按钮 `#16c76f` 96rpx / `--radius-card`；顶部 drag handle |
| CheckoutAuthSheet | `.../CheckoutAuthSheet.vue` | 同上结构，主按钮同样 `#16c76f` |

共享样式原语：`subpkg-order/styles/_shared.scss`

- `.mask`：全屏底、`align-items:flex-end`、`--z-blocking`、`--overlay-dim`
- `.counter-btn` plus=`--brand` 72rpx 圆；minus=`#f3f4f6`
- `.table-status-empty`：本桌订单空态（与 StateEmpty 并存）
- `slide-up` / `ec-card-in` / `ec-shine`

## 3.3 顾客端 — 用户点名的通用类型，当前对应物

| 类型 | 当前事实 | 文件 | 次数 |
|---|---|---|---|
| Button | **没有 Button 组件**。每个页面/弹层自写 class | 见下表 | — |
| Card | `.card-base` 已定义未使用。我的页用 `--radius-hero` + `--card-shadow`；菜卡 20rpx；券卡 24rpx | 分散 | — |
| Modal/Dialog | `uni.showModal`；无自研 Dialog | 多 composable / 页 | 原生 |
| Popup | 底栏 Sheet 家族（上表）；不是 Vant Popup | 见 3.2 | — |
| Toast | 仅 `uni.showToast`（多数 `icon:'none'`） | 无组件 | — |
| Loading | StateLoading（页级）+ LoadingStates（菜单骨架）+ 多处 CSS spinner | 见 3.1 | — |
| Empty | StateEmpty + DishList `.empty-menu` + `_shared` `.table-status-empty` | 三套 | — |
| Tag | DishList `.dish-tag` / `.dish-tag--strong`；商家 `.tag-pending` 等 | 无公共 Tag | — |
| Tab | BottomNav（点餐内）；券列表本地 `.tab-item`；商家 `a-tabs` / TabBar | 三套 | — |
| Navbar | 微信原生 `navigationBar*`。点餐/付款绿底白字，其它页默认 | `pages.json` | — |
| Cell | 我的页 `.service-row`；商家 `.info-row`。`van-cell` 未使用 | 无公共 Cell | — |

**主按钮实际尺寸（不是规范，是现状）**

| 表面 | 高度 | 圆角 | 颜色 | 字重 |
|---|---|---|---|---|
| SpecSheet 确认 | 100rpx（token） | 50rpx（胶囊） | `--brand` | 600 |
| CartBar 去结算 | 92rpx | 46rpx（胶囊） | `--brand` | 600 |
| CheckoutSheet 提交 | 104rpx | 28rpx | `--brand` | 900 |
| StateEmpty / StateError | 88rpx | 24rpx | `#07C160` | 600 |
| entry 进入 | 88rpx | 22rpx | `#16c76f` | 900 |
| MemberChoice 加入 | 96rpx | 24rpx（`--radius-card`） | `#16c76f` | 900 |
| payment-handoff 支付 | 92rpx | 999rpx | `#07c160` | 900 |
| 我的页登录 | 72rpx | 32rpx | 白底绿字 | 700 |

## 3.4 商家端 — 事实标准

| 组件 | 文件 | 引用 | 当前样式 |
|---|---|---|---|
| TabBar | `admin-h5/src/components/TabBar.vue` | Layout（全局） | 高 56px+safe；白底；active `--brand`；字 10px |
| PageHeader | `.../PageHeader.vue` | 约 18 个设置/列表页 | sticky 52px+safe；底边 `#f0f0f0`；标题 17px/700/`#111` |
| StatCard | `.../StatCard.vue` | Dashboard | `a-card`；数字 38px/900/`--text-1` |
| InsightCard | `.../InsightCard.vue` | Dashboard | `a-card` |
| RankList | `.../RankList.vue` | Dashboard | 热销榜 |
| AssistedOrderSheet | `.../AssistedOrderSheet.vue` | OrderManage | `a-drawer` + `a-modal` |
| CameraScanner | `.../CameraScanner.vue` | 核销 | `van-button` |
| 全局 Hero / Section | `styles/global.scss` `.hero-header` `.section-block` `.info-row` `.stat-grid` | Dashboard / More | 绿渐变头、16px 水平节奏 |
| 状态 Tag 类 | `.tag-pending` `.tag-preparing` `.tag-done` `.tag-settled` | global.scss | 红/蓝/绿/灰四套，12px |

**有文件、当前无页面引用（死组件）**

| 文件 | 备注 |
|---|---|
| `NavBar.vue` | 52px 顶栏，与 PageHeader 重复 |
| `DataCard.vue` | 仍用 indigo `$primary-color` + Vant Icon |
| `ListState.vue` | `el-empty`，依赖不在 package.json |
| `CustomTable.vue` / `CustomCheckbox.vue` / `CustomRadio.vue` / `CustomDatePicker.vue` | 只在 `components/index.ts` 导出 |

商家 Button / Modal / Table / Tabs 的事实标准是 **Ant Design Vue**，不是自研。视觉被 `colorPrimary:#07C160` 和 `borderRadius:8` 带着走，和自研 `--radius-card:12px` 不完全同圆角。

---

# 四、弹窗系统（只读参考，不改）

弹窗结构合同已经完成。视觉上它给出了一套 **底栏白卡片** 的样板，但还不是全站唯一皮肤。

## 4.1 分层原则（结构，已落地）

```
CHROME 300  <  FLOATING 850  <  BLOCKING 3100  <  BLOCKING_TOP 3200  <  CRITICAL 4000
```

- 全屏遮罩几何、变暗、z-index、点遮罩关闭 → **BaseOverlay**。
- 标准底栏外壳（位置、表面、顶圆角、max-height、标题/关闭、footer 槽、safe-area）→ **BaseSheet**。
- 业务内容（订单、账单、支付、券）不进 primitive。
- CheckoutSheet 打开时，MemberCheckoutChoice / CheckoutAuthSheet 必须 `blocking-top`（3200 > 3100）。DOM 顺序不是叠层权威。

## 4.2 BaseSheet 已经固定下来的视觉值

| 项 | 实际值 |
|---|---|
| 遮罩 | `--overlay-dim` = `rgba(0,0,0,0.5)` |
| 表面 | `#fff`（这里没走 `--bg-card`） |
| 顶圆角 | `32rpx 32rpx 0 0` |
| 最大高度 | `86vh` |
| 底 padding | `24rpx + env(safe-area-inset-bottom)` |
| 头 padding | `28rpx 36rpx 18rpx` |
| 标题 | 36rpx / 800 / `--text-1` / line-height 1.2 |
| 关闭 | 56rpx 圆，背景 `#f3f4f6`（等于 `--bg-muted` 但写死），字 `--text-3` 28rpx |
| 按钮布局 | **不管按钮**。主按钮仍由业务 footer 自己画 |
| 动画 | 无 |
| 点内容 | 不会触发 mask-click（独立 backdrop 节点） |

## 4.3 还没迁到这套外壳的弹层（视觉差）

| 弹层 | Overlay | 顶圆角 | 高度 | 动画 | 主按钮 |
|---|---|---|---|---|---|
| OrderHistory / TableBill | BaseSheet | 32rpx | 86vh | 无 | 业务 footer |
| MemberChoice / CheckoutAuth | BaseOverlay 直接 | 32rpx | 60vh | 0.2s translateY | `#16c76f` 96rpx |
| CheckoutSheet | `.mask` | 32rpx | 88vh | 无 | 104rpx / 28rpx 圆角 |
| CouponPicker | `.mask` | 32rpx | — | slide-up 0.25s | `--brand` 胶囊 |
| SpecSheet | `.mask` | **40rpx** | 90vh | slide-up 0.25s | `--btn-primary-*` 胶囊 |
| PaymentSuccess / WelcomeCoupon | `.mask` | 各写各的 | — | ec-card-in | `--brand` |

参考标准能抽象出来的「原则」只有这些，而且只对已迁移的两张本桌订单弹层为真：

1. 遮罩半透明黑 50%，不自制 z-index。
2. 底栏贴边，顶两个角 32rpx。
3. 标题重、关按钮是灰圆，不是文字「关闭」。
4. 点遮罩关，点内容不关。
5. 主按钮不进外壳。

不能从中推出全站 Button / Card 规范——外壳自己就不管按钮。

---

# 五、页面一致性分析

## 5.1 顾客端抽查

| 产品页 | 实际实现 | 观察 |
|---|---|---|
| 首页 | `HomeTab.vue` 嵌在 `menu.vue`；`pages/index` 只是进店中转 | 绿头 + 背景图。`pages/index` 声明了一整套 van-* 却不用 |
| 菜单页 | `DishList.vue` | 分类 20rpx 节奏；菜价不走 PriceText；加减不走 AddBtn；空态 PNG |
| 菜品详情 | **不是独立页**，是 SpecSheet | 顶圆角 40rpx，和其它 32rpx 弹层不同；唯一真正用 PriceText/AddBtn 的地方 |
| 购物车 | CartBar + CheckoutSheet | 深色底栏是点餐独有语言；结算页浅灰底 `#f5f7f8` |
| 支付页 | `payment-handoff.vue` + PaymentSuccessSheet | 金额/按钮硬编码 `#07c160`，圆角 999rpx，和结算 28rpx 不同 |
| 订单页 | `subpkg-member/pages/orders.vue` + 本桌 OrderHistorySheet + 我的「最近订单」 | 列表用 State* + `record-card`；本桌用 BaseSheet；我的用 `--radius-hero` 卡。三种订单 UI |
| 会员页 | menu 内 MemberCard Tab；`pages/mine`；`subpkg-member/pages/card.vue` | 会员卡有等级色；我的页身份卡另一套白/金字；`card.vue` 仍硬编码 `#07C160` 头 |

其它顾客页：

- 进店 `pages/entry`：底 `#f5f7fa`（不是 `--bg-page`），按钮 `#16c76f`。
- 券列表：本地 tab 绿底白字、券面红金、state-wrap 圆角 32rpx 阴影 `0 2rpx 12rpx`（不是 `--card-shadow`）。
- 核销 / 取号：大量硬编码 `#07C160`。

## 5.2 商家端抽查

| 产品页 | 实际实现 | 观察 |
|---|---|---|
| 首页 | `Dashboard.vue` | Hero 绿渐变 28px 底圆角 + StatCard + Vant 下拉刷新。这是商家「今日页」语言 |
| 订单 | `OrderManage.vue` | 自制 `.page-header`，不是 PageHeader；统计是内联 `a-row` 不是 StatCard；桌台色：待处理红 / 制作蓝 `#2563eb` / 完成 `#16a34a` / 待支付琥珀 |
| 菜品管理 | `MenuManage.vue` | 同样自制顶栏；分类 chip 本地 `.cat-tag`；大量内联 `#07C160` |
| 会员管理 | `CustomerList.vue` + `CustomerDetail.vue` | 走 PageHeader + Ant 表 |

同功能不同 UI：

- 顶栏：Hero vs `.page-header` vs `PageHeader`。
- 数字卡：StatCard vs 接单页四列内联 vs 菜品 `.summary-bar`。
- 圆角：Ant 8px、token 12px、alert 内联 10px、Hero 28px。

## 5.3 重复实现（已在代码里看到的）

1. 价格：PriceText vs DishList `.dish-price-*` vs HomeTab `.ht-feature-price` vs CartBar `.cart-price`。
2. 加号：AddBtn vs `.counter-btn.plus`。
3. 空状态：StateEmpty vs `.empty-menu` vs `.table-status-empty` vs 商家 `a-empty` / 死代码 `el-empty`。
4. Loading：StateLoading vs LoadingStates vs entry `.loading-ring` vs 核销页 spinner。
5. 关闭按钮：BaseSheet 灰圆 56rpx vs CheckoutSheet 64rpx 无底 vs SpecSheet 88rpx 热区。
6. 商家顶栏两套（三套如果算 Hero）。
7. 品牌绿三条：token / 硬编码 `#07C160` / `#16c76f`。

---

# 六、存在的问题

只列代码里已经发生的事，不发明新视觉。

1. 品牌绿：主 CTA 的 `#16c76f` 已收口到 `--brand`；会员/券页仍有硬编码 `#07C160`。
2. 没有 Button primitive，主按钮高度 72–104rpx、圆角 22 / 24 / 28 / 32 / 46 / 50 / 999 全存在。
3. `.card-base` 定义了却零引用；卡片圆角 20 / 24 / 32 / 36rpx 并存。
4. BaseSheet 是弹层外壳标准，但结账 / 规格 / 券 / 支付成功仍是 `.mask` 各自画壳，圆角和动画已经分叉。
5. PriceText / AddBtn 注释写成「全站唯一」，实际只有 SpecSheet 用。
6. 商家 `variables.scss` indigo 与线上绿品牌并存；死组件还在吃 indigo。
7. 商家 Ant `borderRadius: 8` 与 `--radius-card: 12px` 不一致。
8. 会员/券等业务页仍硬编码 `#07C160`；State* 已在 PHASE-02 改用 token。
9. 小程序 Vant Weapp 注册但不用；商家 Vant + Ant 混用。
10. Toast / Dialog 没有产品层组件，全是微信/浏览器原生，无法统一时长、位置、按钮文案样式。
11. 无 spacing / type scale，字号至少 20 档，字重 600–900 无角色。
12. 订单 / 会员在顾客端有多套页面皮肤。
13. 商家顶栏三套。
14. 暗色只在商家 token 层存在，小程序没有。
15. CartBar `z-index:320` 与 `--z-chrome:300` 只差 20，未走 token。

---

# 七、优化优先级

按「改它对一致性的杠杆」排，不按「好不好看」。**本阶段不实施。**

## P0 — 影响整体一致性的基础问题

1. **收口品牌绿**  
   现存权威值是 `#07C160` / `--brand`。进店与结算授权 CTA 的 `#16c76f` 已改为 `--brand`。剩余债务是会员/券页硬编码同色绿。

2. **主按钮只允许现状里已经出现的少数几种形状，停止再发明第四种高度/圆角**  
   不是现在做 AppButton。P0 是承认没有 Button 系统，禁止再在新代码里写第 8 种 CTA。Constitution 已要求新 CTA 走 `--brand` + `--btn-primary-*`；`--btn-primary-*` 目前只被 SpecSheet 真正使用。

3. **弹层外壳不要再分叉**  
   参考标准已经是 BaseSheet 32rpx / 86vh / 无自制 mask。新底栏弹层不应再复制 `.mask` + 40rpx + 自写 slide-up。旧弹层按 TOUCH_AND_MIGRATE，不是一次迁完。

4. **商家色源只留一套**  
   运行中的权威是 `global.scss` + Ant `colorPrimary #07C160`。`variables.scss` 的 indigo 是过期源。死组件（DataCard / ListState / NavBar）继续让人误以为还有第二套品牌色。

5. **State* 自己先吃 token**  
   页级加载/空/错已经被 Constitution 指定为标准。State* 已改用 token；菜单空态 PNG 等仍是另一套。

## P1 — 多个页面重复出现的问题

1. PriceText / AddBtn 真正接到 DishList / HomeTab / CartBar，或删掉「全站唯一」的注释让重复实现显形。
2. 空状态三套（StateEmpty / empty-menu / table-status-empty）在新页面只准新增其中一套。
3. 顾客订单三入口（我的最近订单 / 本桌弹层 / 订单列表）只统一状态色和金额字号，不改信息架构。
4. 商家顶栏：新页面只用 PageHeader 或只用 `.hero-header` 家族，停止第三种 `.page-header`。
5. 硬编码 `#07C160` 改为 `--brand`（会员子包、券、核销、payment-handoff）。这是替换不是 Redesign。
6. 圆角：新卡片优先 `--radius-card`；新胶囊 999；新底栏 32rpx 顶角。不再新增 20/22/28rpx 除非是已有控件的局部复制。
7. 小程序去掉未使用的 Vant Weapp 注册；商家新代码不要再引入 Vant 控件。

## P2 — 细节优化

1. BaseSheet 表面改用 `--bg-card`、关闭钮改用 `--bg-muted`（现值已经相等，只是没走变量）。
2. CartBar z-index 改读 `--z-chrome` 或明确它属于 chrome 还是更高一档。
3. CheckoutSheet / CouponPicker 迁 BaseSheet 时对齐 32rpx，SpecSheet 40rpx 是产品细节，迁的时候单独决定是否保持。
4. `.card-base` 要么开始用，要么删掉，避免「有公共卡片其实没人用」。
5. 字重：新标题不要再引入 500/bold 第五种写法；维持现有 600/700/800/900 即可。
6. 商家暗色与小程序不对齐——小程序不做暗色也可以，但不要在小程序里复制商家暗色 token 一半。
7. 清理无引用的 admin 组件，避免下次有人从 DataCard 把 indigo 带回来。

---

# 附录 A — 文件地图

| 角色 | 路径 |
|---|---|
| 小程序 token | `member-mini-client/src/styles/global.scss` |
| 小程序入口样式 | `member-mini-client/src/App.vue`（只 import global.scss） |
| 点餐共享原语 | `member-mini-client/src/subpkg-order/styles/_shared.scss` |
| Overlay / Sheet | `member-mini-client/src/components/base-overlay/` `base-sheet/` |
| 页级状态 | `member-mini-client/src/components/state-*` |
| 结构合同 | `member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md` |
| 商家 token | `admin-h5/src/styles/global.scss` |
| 商家过期 SCSS 变量 | `admin-h5/src/styles/variables.scss` |
| 商家 Ant 主题 | `admin-h5/src/App.vue` |

# 附录 B — 审计边界

- 未改任何业务代码、样式、组件、CI。
- 未引入 UI 框架，未改页面布局。
- 未把 BaseSheet 的 32rpx / 36rpx 标题推广成全站新规范；只记录它是弹层参考标准的现有值。
- 次数为静态扫描，不含运行时条件渲染。
- 未做真机视觉走查。颜色和间距以源码为准。
