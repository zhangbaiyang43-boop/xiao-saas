# P1-FRONTEND-DESIGN-SYSTEM-ADOPTION-PHASE-01

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
SCOPE=member-mini-client
CODE_CHANGE=NO
AUTHORITY=
  member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md
  docs/frontend/DESIGN_SYSTEM_CURRENT.md
```

对照已有两份文件，量「落地了多少」，不发明新规范、不设计新组件。

Constitution 已声明：它不是视觉目录；NEW 必须遵守；TOUCHED 只迁相关 primitive；UNTOUCHED 可留。Deferred：AppButton、AppCard、typography/spacing/radius、全量 hex、LoadingStates 并入 StateError。

本文不把 Deferred 写成「现在就要造」。缺口 = 现有 token/primitive 没被用上，或同一元素仍有历史第二套。

---

## 一、当前状态

机器可执行、已经落地的只有 **Overlay / Sheet / layer**。颜色 token 在点餐子包部分落地。Button / Card / Type / Spacing 没有对应 primitive，页面继续各自写。

| 项 | 已有权威 | 落地程度 |
|---|---|---|
| Overlay / z-index | BaseOverlay + layer token + CI allowlist | **高**（结构合同） |
| Bottom sheet 外壳 | BaseSheet | **低**：2 个消费者 |
| Color token | `src/styles/global.scss` `--brand` 等 | **中**：点餐多用 token，会员/券页大量硬编码 |
| `--btn-primary-*` | 同文件 | **低**：2 个文件 |
| StateLoading/Empty/Error | `src/components/state-*` | **中**：会员/券页采用；点餐主路径另有一套 |
| AddBtn / PriceText | Constitution named primitives | **低**：几乎只有 SpecSheet |
| `.card-base` | `global.scss` | **零引用** |
| Typography token | 无（Deferred） | 不适用「未采用」，是未建立 |
| Spacing token | 无（Deferred） | 同上 |
| Radius 完整档 | 仅 `--radius-card` / `--radius-hero` | 部分采用，大量硬编码 |

### 1. Color token

定义：`member-mini-client/src/styles/global.scss` L8–L22。

点餐业务组件多数 `var(--brand)`（DishList、CartBar、CheckoutSheet、CouponPicker、HomeTab、AddBtn 等）。

仍硬编码品牌绿（与 token 同值，未采用变量）：

- `components/state-empty/state-empty.vue` L57、`state-error.vue` L46、`state-loading.vue` L32
- `subpkg-member/pages/{orders,consumptions,growth,points,invite,profile-edit,card,staff-share,consumption-detail}.vue`
- `subpkg-coupon/pages/{list,detail}.vue`
- `subpkg-common/pages/verify-qr.vue`
- `pages/index/index.vue` L139/L184
- `subpkg-order/pages/payment-handoff.vue` L165/L169

第三条绿 `#16c76f`：P1-DESIGN-TOKEN-CONSOLIDATION-PHASE-02 已从 entry / MemberCheckoutChoice / CheckoutAuthSheet 改为 `var(--brand)`。Constitution 仍禁止再复制该值。

`--text-1/2/3`：BaseSheet、MemberCard、State* 在用。会员/券等业务页仍有硬编码灰。

### 2. Typography

无字号/字重 token。各页直接写 `font-size: 22–44rpx`、`font-weight: 600/700/800/900`。这不是「有系统没采用」，是 Constitution Deferred。

重复的是**页面级标题块**，不是缺一个新 Type 组件：`orders.vue` / `consumptions.vue` / `coupon/list.vue` 各自 `.page-header` 绿头 + 白字（例如 `orders.vue` L127–129 `background: #07C160`）。

### 3. Spacing

无 spacing token。padding 现场写 12/16/24/32rpx。会员/券页 `.state-wrap` 拷贝同一套 `margin: 48rpx 24rpx 0; padding: 64rpx 32rpx`（`orders.vue` L147、`list.vue` L241、`consumptions.vue` L116 等）。

### 4. Radius

`--radius-card`（24rpx）用在 CheckoutSheet 卡片、DishList 局部、queue-take、PaymentSuccess 部分按钮、MemberCheckoutChoice 按钮。

`--radius-hero`（36rpx）用在 `mine.vue` 卡片、MemberCard 主 CTA 卡。

未走 token：

- BaseSheet 顶角写死 `32rpx`（`base-sheet.vue` L61）
- SpecSheet `40rpx 40rpx 0 0`
- 菜卡/大量控件 `20rpx`（DESIGN_SYSTEM_CURRENT 计数高于 token）
- 胶囊 `999rpx` / `50%`

### 5. Button

无 AppButton（Deferred）。现有按钮合同只有 `--btn-primary-*`，真正使用：

- `SpecSheet.vue` L522–533
- `queue-take.vue` L304–310

其余主按钮自写高度/圆角/颜色，例如：

| 位置 | 高度 | 圆角 | 色 |
|---|---|---|---|
| CartBar `.checkout-btn` | 92rpx | 46rpx | `--brand` |
| CheckoutSheet `.checkout-btn-full` | 104rpx | 28rpx | `--brand` |
| MemberCheckoutChoice 加入 | 96rpx | `--radius-card` | `--brand` |
| entry `.entry-btn` | 88rpx | 22rpx | `--brand` |
| payment-handoff `.pay-btn` | 92rpx | 999rpx | `#07c160` |
| StateEmpty/Error 按钮 | 88rpx | 24rpx | `--brand` |

AddBtn 是「绿圆加号」primitive，消费者只有 SpecSheet；DishList 仍用 `_shared.scss` `.counter-btn.plus`。

### 6. Card

`.card-base` 只在 `global.scss` L65–70 定义，**业务零引用**。

各页自己写白底+圆角+阴影：`mine.vue` 用 token；`orders.vue` `.record-card` 写死 `border-radius: 24rpx` + `box-shadow: 0 2rpx 12rpx`（L165–172），阴影也不是 `--card-shadow`。

### 7. State 组件

已 import State* 的页面：mine、coupon list/detail、member 的 orders/consumptions/points/invite/growth/profile-edit/card/consumption-detail、OrderHistorySheet、TableBillSheet。

未走 State*：

- 菜单加载：`LoadingStates.vue`（Constitution 允许的独立骨架）
- 菜单空：`DishList.vue` `.empty-menu` + PNG（L48–50）
- 进店：`entry/index.vue` `.loading-ring`
- 核销：`verify-qr.vue` 自绘 spinner
- `_shared.scss` `.table-status-empty` 与 StateEmpty 并存（OrderHistory/TableBill 空态 class 仍叫 table-status-empty，内部已嵌 StateEmpty）

State* 自身已改用 `--brand` / `--text-*` / `--brand-light`（PHASE-02）。

### 8. Overlay / Sheet（对照基线）

已迁 BaseSheet：`OrderHistorySheet.vue`、`TableBillSheet.vue`。

已用 BaseOverlay、未用 BaseSheet：`MemberCheckoutChoice.vue`、`CheckoutAuthSheet.vue`（`layer="blocking-top"`，合法）。

仍 `class="mask"`（`LEGACY_MASK_ALLOWLIST`）：

- `CheckoutSheet.vue`
- `CouponPicker.vue`
- `SpecSheet.vue`
- `PaymentSuccessSheet.vue`
- `WelcomeCouponSheet.vue`

CI：`scripts/check-ui-contracts.mjs` L13–19。

### 9. 页面级重复实现

| 模式 | 出现处 |
|---|---|
| 绿头 `.page-header` | orders / consumptions / coupon list |
| `.state-wrap` 白卡包 State* | 同上 + points / invite / growth / coupon detail |
| 本地主按钮 88–104rpx | 见 Button 表 |
| 本桌空态 class + StateEmpty | OrderHistorySheet L118、TableBillSheet L75 |

---

## 二、重复实现

1. **遮罩**：BaseOverlay vs `_shared.scss` `.mask`（5 个业务 Sheet）。
2. **品牌绿**：`var(--brand)` vs `#07C160` vs `#16c76f`。
3. **主按钮**：`--btn-primary-*` vs 十余处本地 CTA。
4. **加号**：AddBtn vs `.counter-btn.plus`。
5. **价格**：PriceText vs DishList/HomeTab/CartBar 自绘。
6. **空/错/载**：State* vs LoadingStates vs empty-menu vs entry spinner。
7. **卡片**：`.card-base`（死）vs 每页拷贝。
8. **会员子包绿头列表页**：orders / consumptions / coupon list 结构同构。

---

## 三、设计系统缺口

分两类。不把第二类扩成新组件提案。

**A. 已有但没采用（本阶段可迁）**

1. State* 内部改 `var(--brand)` / `--text-*`
2. 会员/券页 `#07C160` → `--brand`
3. 三个 `#16c76f` CTA → `--brand`（Constitution Color 窄条款）
4. 被触摸的 legacy `.mask` Sheet → BaseSheet（TOUCH_AND_MIGRATE）
5. SpecSheet 已用 `--btn-primary-*`；其它新/被改 CTA 跟它走，不新造 AppButton
6. `.card-base` 要么开始用在被改页面，要么删掉以免假装有 Card 系统

**B. Constitution 已 Deferred（不是本次adoption失败）**

- AppButton / AppCard
- typography / spacing / 完整 radius 档
- 全量 hex
- LoadingStates 并入 StateError

---

## 四、迁移优先级

遵守 `TOUCH_AND_MIGRATE`、`BIG_BANG_REWRITE=FORBIDDEN`。只在已有 token/primitive 上收口。

**P0 — 合同已写、现存违反或双轨**

1. `#16c76f` 三处改 `--brand`（entry、MemberCheckoutChoice、CheckoutAuthSheet）— **已在 PHASE-02 完成**
2. State* 自身改用 token（标准组件自己不标准）— **已在 PHASE-02 完成**
3. 新代码禁止再新增 `.mask`（CI 已拦）；触摸 Checkout/Spec/Coupon/Success/Welcome 时迁 BaseSheet 外壳

**P1 — 多页重复、触摸即可收**

1. 会员/券页硬编码 `#07C160` → `--brand` — **已在 PHASE-03 完成**
2. 同构 `.page-header` / `.state-wrap`：改其中一页时抄已采用 token 的写法，不抽新 layout 组件（本阶段禁止设计新组件）
3. DishList 加减：若改到该文件，加号改用已有 AddBtn
4. `--btn-primary-*`：改到某个主 CTA 时用现有 token，不要第三种高度

**P2 — 死代码与 Deferred**

1. `.card-base` 零引用：用或删
2. PriceText 扩到菜卡：仅当改 DishList 时
3. AppButton/Type/Spacing：等单独阶段，不在 adoption 审计里开张

不建议：一次统一全站按钮高度、一次重画所有卡片、为会员列表新建 PageHeader 组件。

---

## 证据路径

| 主题 | 路径 |
|---|---|
| Token 定义 | `member-mini-client/src/styles/global.scss` |
| Overlay CI | `scripts/check-ui-contracts.mjs` |
| BaseOverlay / BaseSheet | `src/components/base-overlay/` `base-sheet/` |
| State* | `src/components/state-*` |
| Legacy mask | CheckoutSheet / CouponPicker / SpecSheet / PaymentSuccessSheet / WelcomeCouponSheet |
| 已迁 Sheet | OrderHistorySheet.vue、TableBillSheet.vue |
| `#16c76f` 已收口 | 业务样式 0 处；Constitution 仍禁止再引入 |
| `--btn-primary-*` | SpecSheet.vue、queue-take.vue |

未改业务代码。影响端：无运行时影响。
