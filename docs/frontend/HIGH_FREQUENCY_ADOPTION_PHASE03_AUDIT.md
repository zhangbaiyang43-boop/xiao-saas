# P1-HIGH-FREQUENCY-ADOPTION-PHASE-03

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
BASELINE=6433b4a
SCOPE=高频路径：菜卡 / CartBar / Checkout / PaymentSuccess + CartBar/CouponBar/LoadingStates layer
CODE_CHANGE=NO
NEW_COMPONENT=NO
NEW_TOKEN=NO
CTA_RULES=UNCHANGED
CARTBAR_VISUAL=UNCHANGED
AUTHORITY=
  docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md
  docs/frontend/CARTBAR_VISUAL_CONTRACT.md
  docs/frontend/PAYMENT_SUCCESS_OVERLAY_DECISION.md
  member-mini-client/src/subpkg-order/components/PriceText.vue
  member-mini-client/src/styles/global.scss
```

对照 **已经冻结** 的合同，看还有哪些能「纯采用」、哪些只是看起来像缺口。不发明档位、不改 CTA、不改 CartBar 视觉。

已冻结合同（本阶段只引用，不重开）：

| 合同 | 内容 |
|---|---|
| PriceText | 现有 sm / md / lg；色 `--brand`；字重 700。md 金额 40rpx = 菜卡。 |
| CartBar | 点餐 Tab 购物车入口 chrome。「去结算」只开 CheckoutSheet。条不进 CTA 体系。深色条 + 白字 48 + 绿胶囊 92 维持。 |
| PaymentSuccess | 结果型底部 Sheet。点遮罩不能关。主动作「关闭并等待」。不能迁当前 BaseSheet。 |
| Overlay | Checkout = BaseSheet `blocking`；CouponPicker = BaseSheet `blocking-top`。Spec / Success / Welcome 仍 `.mask`。 |
| Layer tokens | chrome 300 / floating 850 / blocking 3100 / blocking-top 3200 / critical 4000。禁止本阶段新增 z token。 |

---

## 0. 结论

| 检查 | 结果 |
|---|---|
| 1. PriceText 能否覆盖四表面 | **只能盖住菜卡。** CartBar / Checkout 应付 / 成功实付 对不上现有 sm/md/lg，也没有 inverse / 仪式黑字档。 |
| 2. 金额层级 40 / 48 / 52 / 68 | **四条主表面仍然是这四个数字。** 这是观察阶梯，不是 token，也还没进 PriceText。 |
| 3. CartBar / CouponBar / LoadingStates layer | **三个都不在已命名五档里。** 功能上：CartBar 与 CouponBar 催用条贴着 chrome；LoadingStates 夹在 floating 与 blocking 之间。 |
| 4. 已知合同未采用 | 菜卡价、菜单空/错、Checkout/CouponPicker 外壳、BottomNav/OrderBubble z token **已经采用。** 剩下能静默采用的只剩颜色/格式小债；金额档、CTA、CartBar、Success 外壳 **不是漏用。** |

下一阶段若只做纯采用：不要碰 PriceText 扩档、不要并 CartBar 进 CTA、不要把 Success 套进 BaseSheet。

---

## 1. PriceText 现有能力 vs 四表面

PriceText 现有 API（`PriceText.vue`）：

| size | ¥ | 金额 | 后缀 | 色 / 字重 |
|---|---|---|---|---|
| sm | 22 | **30** | 20 | `--brand` / 700 |
| md | 24 | **40** | 22 | `--brand` / 700 |
| lg | 28 | **44** | 24 | `--brand` / 700 |

另有 `pulse`（缩放，不是改色）、`block`。没有 48 / 52 / 68，没有白字/黑字，没有字重 900。

| 表面 | 现在 | 金额 | 色 / 字重 | 现有 PriceText？ |
|---|---|---|---|---|
| **菜卡** | `DishList.vue` L100–L106 `<price-text size="md">` | **40** | `--brand` / 700 | **已采用 md。** 覆盖。 |
| 首页招牌 | `HomeTab.vue` L48–L51 手写 | 40 | `--brand` / **900**（¥ 28/800） | 尺寸像 md，字重不是。PHASE-02 明确没迁（要先接受 700）。 |
| **CartBar** | 单 text `¥{{ formatPrice }}`（L15、L147–L157） | **48** | **`#fff`** / 700；脉冲 `#34f38a` | **不能。** 无 48 档，无 inverse，脉冲是改色不是 `price-text--pulse`。CartBar 视觉合同禁止改这条。 |
| Checkout 行价 | 拼接 `toFixed(2)`（L45、L293） | 30 | `--brand` / **900** | 金额接近 sm，字重 900≠700，且是行小计不是菜价。 |
| Checkout 已选合计 | L29 | 34 | `--brand` / 900 | 无对应档。 |
| **Checkout 应付** | L86–L88、L356 | **52** | `--brand` / **900** | **不能。** lg 是 44。应付是扣券后价，不是菜价。 |
| **PaymentSuccess 实付** | L10–L12，生效 68rpx（L412–L413） | **68** | **`#111`** / 900 | **不能。** 结果页仪式数字；产品冻结为结果 Sheet，不是绿字菜价。 |
| 成功赠券 | `ec-amount` 68 白字在券红底 | 68 | inverse + 券红 | 不要并进 `--brand` PriceText（Constitution 允许券红）。 |

**结论：** 现有 PriceText 的职责仍是「绿字菜价」。菜卡已接上；CartBar / Checkout 应付 / 成功实付 **不是漏用 md/lg**，是 API 覆盖不到。扩档或 inverse 等于新合同，本阶段禁止。

---

## 2. 金额层级 40 / 48 / 52 / 68

`CARTBAR_VISUAL_CONTRACT.md` 记的阶梯：

> 菜卡价 < 车内合计 < 应付 < 实付  
> 40 < 48 < 52 < 68

当前源码仍对得上：

| 阶 | 表面 | 证据 | 是否 PriceText |
|---|---|---|---|
| 40 | 菜卡 md | `PriceText.vue` L76；DishList 已用 | 是 |
| 48 | CartBar 合计 | `CartBar.vue` L150 | 否（白字手写） |
| 52 | Checkout 应付 | `CheckoutSheet.vue` L356 | 否 |
| 68 | 成功实付（后写覆盖） | `PaymentSuccessSheet.vue` L413 | 否（`#111`） |

**符合。** 这是四条主表面的观察阶梯，不是 token，也没有组件强制。旁边还有别的数字，不破坏这四步：

- Checkout 行 30、已选合计 34
- SpecSheet lg 44（菜价大档，不是应付）
- HomeTab 招牌金额也是 40，但 900
- 成功页前半死规则仍写实付 88rpx，被 L413 盖成 68；产品形态已冻结为底部 Sheet，88 不是生效层级

不要为了「都进 PriceText」去抹平 40/48/52/68。抹平会改 CartBar 视觉或成功页仪式数字，两者都已冻结/禁止。

---

## 3. CartBar / CouponBar / LoadingStates 的 layer

已命名五档（`global.scss` L33–L37）：

```
chrome 300 < floating 850 < blocking 3100 < blocking-top 3200 < critical 4000
```

已采用 token 的：BottomNav `--z-chrome`；OrderBubble 区域 `--z-floating`（hint 仍 851）；Checkout BaseSheet `blocking`；CouponPicker `blocking-top`。

| 表面 | 实际 z | 已有 token？ | 功能归属（观察） |
|---|---|---|---|
| **CartBar** | **320** 字面量（`CartBar.vue` L64） | 否 | 贴在 BottomNav（300）上面的 chrome+。CartBar 合同要求维持 320。改成 `--z-chrome` 会和 Nav 同层。 |
| **CouponBar 催用条** | **319**（`CouponBar.vue` L144 `.coupon-nudge-bar`） | 否 | 固定在车上方、车下方一点。顶栏 `.coupon-bar` **不是** fixed，走文档流，无 z。319 是为了插在 300 与 320 之间。 |
| **LoadingStates** | **2000**（`LoadingStates.vue` L49） | 否 | 菜单骨架/失败遮罩。夹在 floating 850 与 blocking 3100 之间。Constitution 允许菜单骨架独立；没有「内容遮罩」档。升到 blocking 可能盖住不该盖的 sheet；降到 floating 会和 OrderBubble 抢。 |

**结论：** 三者都是 **未命名带**。不是漏写 `var(--z-chrome)` 那种 PHASE-02 替换。塞进现有五档会改叠层。新增第六档 = 新 token，禁止。维持 319 / 320 / 2000。

OrderBubble hint `851` 同理（floating+1，无 token），不在本题三个文件里，顺记。

---

## 4. 高频路径：已知合同未采用？

### 4.1 已经采用（不要再当缺口）

| 合同 | 现状 |
|---|---|
| 菜卡 PriceText md | `DishList.vue` L100–L106 |
| 菜单空 StateEmpty | `DishList.vue` L49，插画走 icon 槽 |
| 菜单错 StateError | `LoadingStates.vue` L4，文案「菜单加载失败」 |
| Checkout 外壳 BaseSheet blocking | `CheckoutSheet.vue` L2–L6 |
| CouponPicker BaseSheet blocking-top | PHASE-05A |
| BottomNav / OrderBubble 层 token | `--z-chrome` / `--z-floating` |
| 品牌绿主填充 | CartBar / Checkout / Success 主按钮已 `var(--brand)` |
| 成功页产品形态 | 底部结果 Sheet；不迁 BaseSheet |

### 4.2 看起来像缺口、其实不能当「漏用」

| 现象 | 为什么不是纯采用 |
|---|---|
| CartBar 不用 PriceText | 48 白字，合同禁止改视觉 |
| Checkout 应付 / 成功实付不用 PriceText | 现有档盖不住；成功页是仪式黑字 |
| CartBar「去结算」不用 `--btn-primary-*` | 入口胶囊 92/46/600，与结算 104/28/900 分家（CartBar 合同 §4） |
| Success 仍 `.mask` | 产品冻结：当前 BaseSheet 会点遮罩关闭 |
| HomeTab 招牌 40/900 不用 PriceText md | 会把字重改成 700，PHASE-02 已列为 DECISION |
| 菜卡加号不用 AddBtn | 60 vs 72，会跳；CTA/高度未拍 |
| `.card-base` 零引用 | 首页卡 32rpx、结算描边卡对不上 24+阴影 |
| CartBar 320 / CouponBar 319 / Loading 2000 不写 token | 见 §3 |

### 4.3 仍是 SPEC_GAP（不扩 API、不改 CTA/CartBar 也能做；本阶段不做）

这些才是「已有合同没被用上」：

| 项 | 已有合同 | 现状 |
|---|---|---|
| 成功实付色 | `--text-1` = `#111827` | `#111`（`PaymentSuccessSheet.vue` L223–L237，接近但未走变量） |
| 结算金额格式 | `formatPrice` | 模板 `toFixed(2)`（行价/应付/已选合计） |
| 分类未选灰、打烊灰 | `--text-3` | DishList / ShopHeader 手写灰 |
| 成功页居中死 CSS、HomeTab 第一套 badge | 后写规则已生效 | 前半仍留着，TOUCH 时可删，不改产品 |

`.tap-shrink` 高频主 CTA 大多未用。给 CartBar 加等于动 CartBar 手感，本阶段禁止。Checkout / Success 可另议，不算本审计必须采用。

---

## 5. 下一阶段（不实施）

**不要做：** PriceText 加档、CartBar 改色/改高/改 z、Success 迁 BaseSheet、新增 z token、统一 CTA 高度。

**若仍要纯采用，只剩 §4.3：** `--text-1` 换掉成功实付 `#111`、结算改走 `formatPrice`、能映射的灰改 `--text-3`、删成功页/HomeTab 死 CSS。

金额 40/48/52/68 保持观察阶梯，直到有单独「金额档」阶段（那会动 PriceText API，需另开）。

---

## 6. 本阶段没做

- 没有改任何 `.vue` / `.scss` / token。
- 没有创建组件。
- 没有修改 CTA 规则或 CartBar 视觉。
- 没有把 40/48/52/68 写成新 Design Token。
