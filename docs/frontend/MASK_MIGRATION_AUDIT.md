# P1-DESIGN-SYSTEM-CLEANUP-PHASE-04

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
BASELINE=3687970
SCOPE=legacy .mask 五处 + .card-base / AddBtn / PriceText 重复实现
CODE_CHANGE=NO
NEW_COMPONENT=NO
NEW_TOKEN=NO
DELETE=NO
AUTHORITY=
  member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md
  docs/frontend/DESIGN_SYSTEM_CURRENT.md
  docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md
```

对照已有 Overlay / BaseSheet 合同，给 legacy `.mask` 分类。不发明新 primitive、不改代码、不删样式。

三类含义：

| 标记 | 含义 |
|---|---|
| **必须迁 BaseSheet** | 当前 BaseSheet API（底栏、标准标题+关闭、mask-click → `close`、`#footer`）已经装得下。下一阶段只迁外壳，业务内容不动。 |
| **暂时保留** | 现在硬套 BaseSheet 会改结构或必须先扩 BaseSheet。`.mask` 可继续留在 `LEGACY_MASK_ALLOWLIST`。下次 TOUCH 只迁相关 primitive（通常是 BaseOverlay，不是 BaseSheet）。 |
| **需要产品决策** | 迁不迁会改变顾客能点什么、第一眼看到什么。工程不能替产品选。 |

「必须迁」不是本审计阶段动手，是指定后续 overlay 阶段的目的地。Constitution 仍是 TOUCH_AND_MIGRATE，禁止五张一起 BIG_BANG。

已迁对照（不在本范围）：`OrderHistorySheet.vue`、`TableBillSheet.vue` 已走 BaseSheet → BaseOverlay，`layer="blocking"`。

---

## 0. 遗产名单（机器合同）

`member-mini-client/scripts/check-ui-contracts.mjs` `LEGACY_MASK_ALLOWLIST`（正好五条，与本范围一致）：

1. `subpkg-order/components/CheckoutSheet.vue`
2. `subpkg-order/components/CouponPicker.vue`
3. `subpkg-order/components/PaymentSuccessSheet.vue`
4. `subpkg-order/components/SpecSheet.vue`
5. `subpkg-order/components/WelcomeCouponSheet.vue`

`.mask` 定义：`subpkg-order/styles/_shared.scss` L11–L17。`position:fixed; inset:0; z-index: var(--z-blocking); background: var(--overlay-dim); align-items: flex-end`。

DishList / CartBar / OrderHistory / TableBill 也 `@import _shared.scss`，但没有 exact class token `mask`（给 `.counter-btn` 等）。**不要**因为 import 了 shared 就把它们当 mask 消费者。

同文件但不是 `.mask`：`WelcomeCouponSheet.vue` 的 `.closed-mask`（`z-index: 3000`，已在 `LEGACY_RAW_BLOCKING_ALLOWLIST`）。见 §2.5。

---

## 1. 分类总表

| 表面 | 形态 | mask 点击 | 标准头（标题+关闭） | 分类 |
|---|---|---|---|---|
| CheckoutSheet | 底栏 sheet，有 footer CTA | 关闭 | 有 | **必须迁 BaseSheet** |
| CouponPicker | 底栏 sheet，列表 | 关闭（emit `cancel`） | 有 | **必须迁 BaseSheet** |
| SpecSheet | 底栏 sheet + 全宽英雄图 | 关闭（emit `cancel`） | 无（关闭钮叠在图上） | **暂时保留** |
| PaymentSuccessSheet | 底栏 sheet 套仪式卡；文件里还有一套居中 modal 死 CSS | **无** | 无（只有 handle） | **需要产品决策** |
| WelcomeCouponSheet（券卡） | **居中**营销卡，不是底栏 | 关闭 | 无 | **暂时保留**（不要迁 BaseSheet） |

---

## 2. 逐张

### 2.1 CheckoutSheet — 必须迁 BaseSheet

路径：`member-mini-client/src/subpkg-order/components/CheckoutSheet.vue`

- 外壳：`<view class="mask" @click="$emit('close')">` + 内层 `@click.stop`（L2–L3）。
- 头：标题 `confirmationText.title` + `icon-close`（L4–L6），与 BaseSheet 头同构。标题已经 36rpx（L185），BaseSheet 标题也是 36rpx/800（`base-sheet.vue` L93–L97）。
- 身：`scroll-view.order-confirm-content`（L8）。
- 脚：`.order-confirm-bottom` 主 CTA（L94–L98）→ 对应 BaseSheet `#footer`。
- 顶角 32rpx（L172）= BaseSheet 表面 32rpx（`base-sheet.vue` L61）。max-height 88vh vs BaseSheet 86vh，差 2vh，属外壳数字，迁壳时跟第一家族对齐即可。
- 叠层：`menu.vue` L198–L239 与 CouponPicker / Auth / Choice 同时存在。Auth / Choice 已是 BaseOverlay `blocking-top`（3200）。Checkout 迁成 BaseSheet `blocking`（3100）后，**3200 > 3100 这条已有合同继续成立**。

迁的时候只换壳：

```
mask + cart-sheet  →  <base-sheet layer="blocking" :title="..." @close="$emit('close')">
body               →  default slot
order-confirm-bottom →  #footer
```

去掉内层 `@click.stop`（BaseOverlay 用独立 backdrop 节点，Constitution TEST J）。

视觉差（接受为外壳对齐，不是产品分叉）：

- 表面底色现在 `#f5f7f8`（L171），BaseSheet 是 `#fff`。内卡自己仍是白。第一家族（本桌订单）已经是白底。
- 标题字重 900 vs BaseSheet 800。

不要在这次迁 CTA 高度（104rpx）——那是 `HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md` 的 OPEN 项。

### 2.2 CouponPicker — 必须迁 BaseSheet

路径：`CouponPicker.vue`

- 外壳：`.mask` `@click="$emit('cancel')"`（L2–L3）。
- 头：标题「优惠券」+ 关闭（L4–L7）。标题 32rpx/900（L132–L137），BaseSheet 是 36rpx/800。迁壳后字号会跟第一家族对齐，这是外壳合同，不是券业务。
- 身：列表；空态是 `.cp-empty` 一行字（L57），**不是**页级 empty，不必接 StateEmpty。
- 无独立 footer。
- 顶角 32rpx / max-height 76vh（L111–L116），有 `slide-up`。BaseSheet **没有**入场动画（`DESIGN_SYSTEM_CURRENT.md`）。迁壳会丢掉 0.25s slide-up。这是外壳对齐，不是产品分叉。
- emit 名是 `cancel` 不是 `close`。消费者里写 `@close="$emit('cancel')"` 即可，和 OrderHistory 一样适配，不必改 menu 业务事件名。

**叠层（已有合同，不是新决策）：** 打开时结算仍在（`menu.vue` L199 `v-if="showCart"` 与 L241 `v-if="showCouponPicker"` 双真）。现在两张都是 `.mask` → 都是 3100，全靠 DOM 后写的 CouponPicker 压住。Constitution：「DOM 不是叠层权威」「叠在结算上的选择/鉴权层用 `blocking-top`」。券选择器与 Auth/Choice 同类，迁 BaseSheet 时应用 `layer="blocking-top"`，不要继续 3100 + DOM 顺序。

建议顺序：CouponPicker 先于 CheckoutSheet（先把 3200 的第二层落到合同上；Checkout 仍是 3100 的 `.mask` 也能被压住）。

### 2.3 SpecSheet — 暂时保留

路径：`SpecSheet.vue`

为什么现在不是 BaseSheet 目的地：

1. **英雄图占掉标准头。** 全宽 `.spec-detail-hero` 在标题前（L4–L15）。关闭是绝对定位叠在图上（L220–L232，88rpx 热区），不是 BaseSheet 那颗 56rpx 灰圆关闭。
2. BaseSheet 头不可关。`showClose=false` 且 `title=""` 仍会留下 `.base-sheet-head` 的 28/36/18 padding（`base-sheet.vue` L69–L77）。硬套会在英雄图上方多一条空白头。
3. 顶角 **40rpx**、max-height **90vh**（L149–L151），第一家族是 32rpx / 86vh。
4. `.spec-sheet` 自己 `position: fixed; bottom:0`（L143–L147），等于在 `.mask` 里又做了一遍 overlay 几何。
5. 主按钮已经走 `--btn-primary-*`（L520–L536）。加减是 minus 用 `_shared.scss` `.counter-btn`、plus 用 `AddBtn`（L64）——业务控件，与壳无关。

Constitution：「特殊 blocking overlay 可以只用 BaseOverlay」；「禁止要求每个 BaseOverlay 消费者都用 BaseSheet」。

建议（仍不实施）：

- **暂时保留 `.mask`。** 不要为 Spec 去扩 BaseSheet（headerless / 英雄图槽 = 新能力，本阶段禁止新组件/新 API）。
- 下次 TOUCH 这张壳时，只把 `.mask` 换成 BaseOverlay `layer="blocking"`，自研表面留在 slot 里。那是 overlay primitive，不是 BaseSheet。
- 40rpx vs 32rpx 不要在清理阶段偷偷改。

### 2.4 PaymentSuccessSheet — 需要产品决策

路径：`PaymentSuccessSheet.vue`

与标准底栏 sheet 的差异（都会变成顾客可感知行为）：

1. **遮罩不能关。** L2 `<view class="mask success-mask">` 没有 `@click`。注释 L97–L99 写明保持「只有里面的按钮能关」。BaseSheet 写死 `@mask-click="$emit('close')"`（`base-sheet.vue` L2）。套上之后点暗处就会关成功页。
2. **没有标准头。** 只有 `.success-handle`（L4）+ 居中仪式卡（勾、实付、状态条、三按钮）。没有标题行、没有关闭钮。
3. **文件里两套布局。** 先写居中卡 40rpx（L132–L148），后写底栏 sheet（L326–L344）把 mask 改成 `flex-end`。生效的是底栏；前半是死 CSS（`HIGH_FREQUENCY_UI_AUDIT.md` §7B）。迁壳前必须先定「底栏 sheet 还是居中卡」，否则会改错套。
4. 成功页打开时结算通常已关，但仍可能和券提醒等并存。没有「点遮罩 = 关闭」的现有合同。

要产品拍的两问（拍完才能选目的地）：

| 问 | 若选 A | 若选 B |
|---|---|---|
| 点遮罩能否关闭成功页？ | 能 → 才允许 BaseSheet | 不能 → 禁止用当前 BaseSheet；只用 BaseOverlay，mask-click 不绑 close |
| 第一眼是底栏 sheet 还是居中仪式卡？ | 底栏 → 外壳可向第一家族靠 | 居中 → 不是 BaseSheet；走 BaseOverlay 居中 slot |

在这两问拍板前：**暂时把 `.mask` 留在 allowlist。** 不要「顺便」改成 BaseSheet。不要在清理阶段删那套居中死 CSS（用户要求本阶段不删）。

### 2.5 WelcomeCouponSheet — 暂时保留（禁止迁 BaseSheet）

路径：`WelcomeCouponSheet.vue`

券卡（L1–L15）才是 allowlist 上的 `.mask`：

- `.welcome-mask` 把 `.mask` 改成 **居中** + `padding: 0 48rpx` + 遮罩色 `rgba(15,23,42,.58)`（L135–L140），覆盖了 shared 的 `flex-end` 和 `--overlay-dim`。
- 内容是红金营销卡（Constitution 允许券红），不是底栏 sheet。
- 点遮罩会 `close`（L2）。无标题头。

把这张改成 BaseSheet = 从居中券卡变成底栏白 sheet，是产品改版，不是外壳迁移。

建议：

- **暂时保留 `.mask`。** 目的地若有，是 **BaseOverlay 直连**（居中 slot），不是 BaseSheet。
- 同文件 `.closed-mask`（L17–L25、L59–L68）：`position:fixed; inset:0; z-index:3000`。**不是** exact token `mask`，所以不在五张名单里，但在 `LEGACY_RAW_BLOCKING_ALLOWLIST`。3000 不是五档 layer token（夹在 850 与 3100 之间，且 **低于** `.mask` 的 3100）。打烊遮罩若与结算同时出现，会被结算盖住。这是相邻债：下次 TOUCH 走 BaseOverlay；**不要**为此新增 z token。打烊卡也是居中，同样不要套 BaseSheet。

---

## 3. 建议迁移顺序（仍不实施）

1. **CouponPicker** → BaseSheet `blocking-top`（先修「压在结算上却同 3100」）。
2. **CheckoutSheet** → BaseSheet `blocking` + `#footer`。
3. 从 `LEGACY_MASK_ALLOWLIST` 去掉已迁路径；CI `base-sheet.contract.test.js` TEST G 会要求改期望数组。
4. Spec / Welcome：保持 allowlist；TOUCH 时只迁 BaseOverlay。
5. Success：等 §2.4 两问。

禁止：五张同一 PR；顺手改 CTA / CartBar / 加号尺寸；扩 BaseSheet 变成万能壳。

`_shared.scss` 的 `.mask` **不要删**，直到 allowlist 为空。

---

## 4. 无引用 / 重复实现（只建议，不删）

### 4.1 `.card-base` — 定义了，业务零引用

定义：`member-mini-client/src/styles/global.scss` L65–L70（白底 + `--radius-card` + `--card-shadow`）。

全 `member-mini-client` 只有这一处出现 `card-base`。

建议：

- **不要删。** 这是已有卡片合同，不是死代码包袱。
- 下次 TOUCH 菜卡/结算卡/首页卡时，能对上 24rpx+阴影的再套这个类（菜卡已经手写了同一组 token，见 `DishList.vue` `.dish-item`）。
- 套不上的（首页 32rpx 自制阴影、结算描边卡）不要为了用类而改圆角——那是 `HIGH_FREQUENCY_UI_AUDIT.md` 的 DECISION。

### 4.2 AddBtn — 有引用，但加号仍有第二套

文件：`subpkg-order/components/AddBtn.vue`。md=72rpx 圆，sm=52rpx。

唯一消费者：`SpecSheet.vue` L64 / L86–L90（数量 plus）。

同一条路径上的第二套：

| 位置 | 实现 | 尺寸 |
|---|---|---|
| SpecSheet plus | AddBtn md | 72rpx |
| SpecSheet minus | `_shared.scss` `.counter-btn` | 72rpx |
| DishList 加号 | `.dish-counter .counter-btn.plus` | **60rpx**（`DishList.vue` L637） |
| CheckoutSheet 行内加减 | `.counter-btn.plus.sm` / `.minus.sm` | 52rpx（shared `.sm`） |

建议：

- **不要删 AddBtn。** 它是 Constitution 点名的 primitive。
- **不要**在清理阶段把 DishList 60rpx 改成 AddBtn 72rpx（视觉会跳）。高度差已记在 `HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md` / 审计 §1。
- Checkout 行内 52rpx 已经对齐 AddBtn sm。若下次 TOUCH 结算行，**建议** plus 改 AddBtn sm、minus 仍用 shared（AddBtn 没有减号，自身注释也这么写）。这是采用，不是新组件。
- SpecSheet 已经 plus=AddBtn、minus=counter-btn，保持。

### 4.3 PriceText — primitive 在用；重复实现不要删

PriceText 三档（`PriceText.vue`）：sm 22/30/20、md 24/40/22、lg 28/44/24；色 `--brand`；字重 700/后缀 500。

已采用：

- `DishList.vue` 菜卡 `size="md"`（PHASE-02）
- `SpecSheet.vue` 头价 `size="lg"`

仍手写（重复实现）。**不要删这些样式**，多数档位对不上现有 sm/md/lg：

| 表面 | 现状 | 能否直接换 PriceText |
|---|---|---|
| HomeTab 招牌 | ¥ 28/800 + 金额 40/900 + 后缀 24/700（`HomeTab.vue` L48–L51、L414–L420） | 不能静默换 md（字重 900 vs 700，¥ 更像 lg）。**DECISION** |
| CartBar 合计 | 单 text 白字 48rpx（`CartBar.vue` L15、L146–L157） | 不能。无 inverse 档；CartBar 视觉冻结 |
| Checkout 行价 | 30rpx/900 拼接 `toFixed(2)`（L45、L293） | 接近 sm 的 30，但字重 900、且是「小计」不是菜价 |
| Checkout 已选合计 | 34rpx/900（L30、L266） | 无对应档 |
| Checkout 应付 | 52rpx/900（L89、L366–L369） | 无对应档 |
| 成功实付 | 68rpx/`#111`（`PaymentSuccessSheet.vue` L12、L412） | 无对应档；成功页仪式数字 |
| 成功赠券 / 欢迎券 | 68–88rpx 白字在券红底（`ec-amount` / `wc-amount`） | 券面允许红金；不要并进 `--brand` PriceText |

建议：

- **不要删 PriceText，也不要删上述手写价。**
- 只有「绿字菜价、尺寸已是 md/lg」才建议下次 TOUCH 时换组件。HomeTab 招牌要先接受 700 字重，或接受扩档（扩档 ≈ 新 API，需单独阶段，本清理禁止）。
- 应付/实付/车内白字：等 CTA/CartBar 决策，不要借清理混进 PriceText。

---

## 5. 明确不在本审计删改范围

- `MemberCheckoutChoice` / `CheckoutAuthSheet`：已是 BaseOverlay，无 `.mask`。
- LoadingStates `z-index: 2000`、CartBar `320`、CouponBar `319`：layer 无名带，见高频审计；不是 `.mask`。
- AppButton / AppCard / spacing / type scale：Constitution Deferred。
- 成功页死 CSS、HomeTab 失效 badge 第一套：工程债，本阶段「不要删除」。

---

## 6. 本阶段没做

- 没有改任何 `.vue` / `.scss` / allowlist / token。
- 没有创建组件、没有扩 BaseSheet API。
- 没有删除 `.card-base`、AddBtn、PriceText、手写价、`.mask`。
- 没有把 OPEN 的 CTA / CartBar 决策当成已采纳。
