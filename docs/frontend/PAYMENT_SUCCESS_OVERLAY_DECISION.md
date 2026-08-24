# P1-PAYMENT-SUCCESS-UX-DECISION-PHASE-01

```
STATUS=FROZEN
DATE=2026-08-24
BASELINE=40bf888
CODE_CHANGE=NO
BASESHEET_MIGRATION=NO
NEW_COMPONENT=NO
AUTHORITY=本文件冻结支付成功 overlay 的产品合同
SOURCE=
  member-mini-client/src/subpkg-order/components/PaymentSuccessSheet.vue
  member-mini-client/src/subpkg-order/pages/menu.vue
  member-mini-client/src/subpkg-order/utils/orderText.js
  docs/frontend/MASK_MIGRATION_AUDIT.md §2.4
  docs/frontend/ORDER_ENTRY_AUDIT.md §1.4
```

只冻结产品定位。不改代码、不迁 BaseSheet、不新增组件。后续 overlay 清理必须遵守本文，不得把成功页「顺便」改成标准 BaseSheet。

---

## 冻结结论

| 问 | 决定 |
|---|---|
| 1. 是否允许点击遮罩关闭？ | **不允许。** 只能点成功页里的按钮离开。 |
| 2. 成功页属于哪一种？ | **A 底部 Sheet。** 不是居中成功卡，也不是独立结果页。 |
| 3. 用户下一步核心动作？ | **关闭并等待**（留下堂食、等商家接单/出餐）。「继续加菜」是第二动作；「查看本桌订单」是第三动作，打开本桌实时弹层。**没有「返回首页」。** |

---

## 1. 点击遮罩关闭？不允许

### 当前实现

`PaymentSuccessSheet.vue` L2：

```html
<view class="mask success-mask">
```

没有 `@click`。内层 `success-sheet` 有 `@click.stop`（L3），即使将来有人给 mask 加点击，点卡片也不会冒泡。

组件注释写死了产品意图（L97–L99）：

> 原模板的遮罩层本身没有点击关闭的 `@click`，只有里面的按钮能关闭弹层，这里保持一致，没有加 mask 点击事件。

关掉成功页只有三条 emit，都来自按钮（L75–L83）：

- `close-and-wait` → `menu.vue` `closeSuccessAndWait`（L846–L848）→ `finishOrdering`
- `continue-ordering` → `continueOrdering`（L850–L868）
- `view-order-detail` → `viewOrderDetail`（L870–L878）

三条路径行为不同：前两条在非 `successPreserveDraft` 时会清空购物车；第三条**故意不动购物车**，并 `showOrders = true`。点遮罩无法表达这三种结果。

`successText.safeTip`（`orderText.js` L32）：「订单状态会自动更新，无需重复提交或再次支付。」成功页是付钱之后的确认面，不是可随手划掉的挑规格层。

### 对 overlay 的约束（不实施，只锁死）

当前 BaseSheet 写死 `@mask-click="$emit('close')"`（`base-sheet.vue` L2）。**成功页因此不能迁到现有 BaseSheet。** 这与 `MASK_MIGRATION_AUDIT.md` §2.4 一致：不允许点遮罩关闭 → 禁止用当前 BaseSheet；以后若迁 overlay，走 BaseOverlay，且 **mask-click 不绑定 close**。

Welcome 券卡点遮罩会关（`WelcomeCouponSheet.vue` L2）。那是营销打断，不是付钱确认。两张不要对齐成同一套关闭规则。

---

## 2. 形态：A 底部 Sheet

三个选项对照当前事实：

| 选项 | 是否当前事实 | 决定 |
|---|---|---|
| **A 底部 Sheet** | 是（后写、生效的样式） | **冻结为此** |
| B 居中成功卡 | 文件前半有死 CSS，运行时被覆盖 | 否 |
| C 独立结果页 | 没有路由；`v-if="showSuccess"` 挂在 `menu.vue` L282 | 否 |

生效布局（后写覆盖前写，`PaymentSuccessSheet.vue` L326–L354）：

- `.success-mask`：`align-items: flex-end`（贴底）
- `.success-sheet`：全宽、顶圆角 `32rpx 32rpx 0 0`、`max-height: 88vh`
- `.success-handle`：顶栏拖柄

这是底栏 sheet 外壳。里面的 `.success-card`（勾、实付、三按钮）是 **sheet 里的内容卡**，不是第二种 overlay。

文件前半（L132–L148）仍是居中卡（`align-items: center`、圆角 40rpx）。`HIGH_FREQUENCY_UI_AUDIT.md` 和 mask 审计已标明这是死 CSS。产品形态冻结为 A 之后，删除前半居中规则属于工程清理，**不是改产品**；本阶段仍不删。

不选 B：把成功页改回居中，是改版，不是承认现状。

不选 C：成功页必须留在当前桌台会话里。`viewOrderDetail` 依赖同一页的 `showOrders` / `myOrders_{shop}_{table}_{session}`；`continueOrdering` 把 `activeTab` 设回 `'order'`。独立结果页会拆掉桌台会话、本桌弹层和购物车草稿（`successPreserveDraft`）这套合同。

---

## 3. 下一步动作：核心是「关闭并等待」

### 当前三个按钮（视觉层级 = 产品层级）

文案权威：`orderText.js` `successText`（L22–L32）。模板顺序：`PaymentSuccessSheet.vue` L74–L83。

| 层级 | 文案 | 样式 | 处理 | 结果 |
|---|---|---|---|---|
| **主按钮** | 关闭并等待 | `.success-btn-primary` | `closeSuccessAndWait` → `finishOrdering` | 关成功页；非草稿恢复时清空购物车；toast「已关闭，请安心等待」；**继续轮询已支付单**（`menu.vue` L843） |
| 次按钮 | 继续加菜 | `.success-btn-secondary` | `continueOrdering` | 关成功页；同样按草稿规则处理购物车；切到点餐 Tab；toast「已返回点餐页」 |
| 幽灵按钮 | 查看本桌订单 | `.success-btn-ghost` | `viewOrderDetail` | 关成功页；**不清购物车**；`showOrders = true` 打开本桌 Sheet，**不进**会员「我的订单」`orders.vue` |

「查看本桌订单」已在订单入口阶段从「查看订单详情」改过（`mine-orders-entry.test.js` 锁定文案）。它看的是这桌这轮会话的实时单，不是历史订单中心（`ORDER_ENTRY_AUDIT.md` §1.4，处理函数未改）。

没有「返回首页」按钮。成功遮罩盖住 `BottomNav`。主路径结束后人仍在点餐页，等出餐——这就是堂食。

### 对所给三个候选的裁定

| 候选 | 裁定 |
|---|---|
| 查看本桌订单？ | **第三动作。** 需要看进度时才点。不是付完钱的默认下一步。 |
| 继续点餐？ | **第二动作。** 文案是「继续加菜」，不是回首页。仍在本桌会话。 |
| 返回首页？ | **不是成功页出口。** 禁止把主按钮改成回 HomeTab / `pages/index` / 我的。那会离开本桌等待。 |

标题是「下单成功」（`successText.title`），不是「支付凭证页」。主 CTA「关闭并等待」+ 底栏 tip「状态会自动更新」= 付钱之后的默认下一步是 **留下、等商家**。

---

## 4. 后续 overlay 阶段必须遵守

1. 成功页继续留在 `LEGACY_MASK_ALLOWLIST`，直到改走 **BaseOverlay 且 mask-click 不关页**。
2. **禁止**迁到当前 BaseSheet（会变成点遮罩就关）。
3. 形态保持 **底部 Sheet**；不要改成居中卡或新页面路由。
4. 三按钮层级、文案职责、本桌 vs 会员订单分流，不在 overlay 清理里改。
5. 前半居中死 CSS 可以在以后 TOUCH 本文件时删，不改变冻结的 A。

本阶段没有改任何 `.vue` / `.scss` / allowlist。
