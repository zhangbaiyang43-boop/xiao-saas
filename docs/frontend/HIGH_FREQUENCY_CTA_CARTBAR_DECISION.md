# 高频路径 CTA / CartBar 设计决策（未实现）

```
STATUS=OPEN
DATE=2026-08-24
BASELINE=b65ea37
AUTHORITY=NOT Constitution, NOT a token, NOT to implement in PHASE-02
SOURCE=docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md §1 / §7B / §8.1 / §10
```

PHASE-02 只做已有合同采用。主 CTA 高度、圆角、字重，以及 CartBar 深色方案，**本文件只记录选项，不落地、不新增 token、不创建 AppButton**。

拍板之前，代码继续维持现状：

| 表面 | 现状（禁止本阶段改） |
|---|---|
| 菜单选规格 | 60rpx / 胶囊 30rpx / 24rpx / 600 |
| 购物车「去结算」 | 92rpx / 胶囊 46rpx / 32rpx / 600 / 深底 |
| 结算提交 | 104rpx / 方 28rpx / 34rpx / 900 / 浅底 |
| 支付成功主按钮 | 98rpx / `--radius-card` / 32rpx / 900 |
| 规格确认 | `--btn-primary-*` 100 / 50 / 32 / 600 |
| CartBar 条 | `#1f2937` 空 / `--text-1` 有货；`z-index: 320` |

---

## 决策 1：主 CTA 家族

问题：五步相邻的主按钮不是同一形状。已有 `--btn-primary-*` 只是 SpecSheet 回溯值，**不是**全路径已采纳的视觉标准。

| 选项 | 内容 | 代价 |
|---|---|---|
| A. 全部改成 `--btn-primary-*` | 100rpx 胶囊、32rpx、字重 600 | 结算 104/方/900、成功 98/`--radius-card`/900、CartBar 92 胶囊都会明显变样 |
| B. 维持路径各写各的 | 现状 | 视觉不连续；禁止假装「漏用了 token」 |
| C. 两套家族（建议后续拍板） | **Chrome 胶囊**：CartBar / 菜单选规格，贴在深色或列表控件上。**Sheet 满宽方按钮**：结算 / 成功 / 规格确认，贴在浅色底栏弹层上。首页 Hero 反相白底绿字算第三套「营销 Hero」，不并进主 CTA | 要写清两套各自的高度/圆角/字重；仍可能要扩 `--btn-primary-*` 或等 AppButton（Deferred） |

**建议（未采纳）：C。** 不要把 CartBar 胶囊改成结算的方按钮，也不要把结算改成 100rpx 胶囊，除非产品明确要「一条路径一种按钮」。

未决细节（C 若被采纳仍要定）：

- 胶囊高度用 92（车）还是 60（选规格）还是 token 100
- 方按钮高度用 104 还是 98 还是 100
- 字重 600 vs 900 哪套属于「付钱」

---

## 决策 2：CartBar 深色方案

问题：菜单列表浅底，CartBar 突然 `#1f2937`，BottomNav 又是白。结算 sheet 回到浅底。这是整条高频路径最大的家族分裂。

| 选项 | 内容 | 代价 |
|---|---|---|
| A. 保留深色（建议后续拍板） | CartBar 继续当「强调条」：白字大价 + 绿胶囊。结算/成功保持浅色 sheet | 与浅色页不是一家，但点餐 App 常见；PHASE-02 已冻结此方案 |
| B. 改成浅色底栏 | 与结算 sheet、BottomNav 一家；价格改回品牌绿 | 合计数字在浅底上不如深底抢；要重做空态灰、badge、disabled `#4B5362` |
| C. 深色只在「有货」时出现 | 空车浅/白，有货再深 | 空/满切换会闪；交互决策，不只是色 |

**建议（未采纳）：A。** 深色 CartBar 是点餐主路径的强调条，不是漏用 `--bg-card`。要改成 B 必须单独做视觉稿，不能当 token 采用。

未决细节（若维持 A）：

- 白字 48rpx 合计要不要进 PriceText 新档（扩 API ≈ 新规范，需单独阶段）
- CouponBar 催用条 `z-index: 319` 贴在车上方是否保持

---

## 明确不是本决策范围

- AppButton / AppCard（Constitution Deferred）
- 新增 color / spacing / z-index token
- LoadingStates `z-index: 2000` 无名带（layer 合同扩展）
- Checkout / Success 迁 BaseSheet（overlay 债）
- HomeTab 招牌价 40rpx/900 是否并进 PriceText md（会改字重）

拍板方式：产品确认选项编号后，另开阶段 TOUCH_AND_MIGRATE，禁止顺手改未点名的按钮。
