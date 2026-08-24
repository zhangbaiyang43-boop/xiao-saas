# MINI UX POLISH AUDIT

```
MODE=READ_ONLY_AUDIT
DATE=2026-08-24
BASELINE=d7249cf
SCOPE=member-mini-client 顾客端上线前体验
CODE_CHANGE=NO
PHASE-01=P1-MINI-UX-POLISH-IMPLEMENTATION-PHASE-01 已补：打烊/空菜单 toast；历史订单卡 toast。未做详情页。
NEW_COMPONENT=NO
NEW_TOKEN=NO
AUTHORITY=
  member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md
  docs/frontend/DESIGN_SYSTEM_CURRENT.md
  docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md
  docs/frontend/HIGH_FREQUENCY_ADOPTION_PHASE03_AUDIT.md
  docs/frontend/ORDER_ENTRY_AUDIT.md
  docs/frontend/CARTBAR_VISUAL_CONTRACT.md
  docs/frontend/PAYMENT_SUCCESS_OVERLAY_DECISION.md
```

不是重做 UI。不是扩大 Design System。只找 **真实使用** 会被卡住、被误导、或点了没反应的问题。

分类：A 用户明显感知 / B 同一任务行为不一致 / C 视觉细节 / D 技术债（不当用户问题）。  
优先级：P0 影响上线主任务 / P1 建议优化 / P2 长期。

---

## 1. 当前用户路径地图

冷启动 `pages/index`：有店+桌进 `menu.vue`，否则提示扫桌上点餐码。`menu.vue` 默认 Tab 是 **点餐**（`activeTab = 'order'`，L653），不是 HomeTab。

```
扫码 / index
  → menu（DishList + CartBar + BottomNav）
      首页 HomeTab ← 底栏第一个图标
      点餐 DishList ← 默认着陆
      会员 MemberCard ← 第三个图标
      我的 → navigateTo pages/mine（独立页，不是 Tab 内容）
  → CartBar「去结算」→ CheckoutSheet（确认，不是第二菜单）
  → 微信支付
  → PaymentSuccessSheet（结果型底部 Sheet）
      关闭并等待 / 继续加菜 / 查看本桌订单（本桌 Sheet）
```

查看订单（已收口）：

```
点餐中：OrderBubble / 成功页「查看本桌订单」→ OrderHistorySheet | TableBillSheet
        数据 = 本桌本会话 myOrders

离开后：我的 → 我的订单 / 最近订单卡片 → subpkg-member/pages/orders
        数据 = GET /v1/member/orders（历史，无菜品行，卡片不可点）
```

会员：

```
BottomNav 会员 → MemberCard → 成长 / 积分 / 优惠券列表
我的 → 等级行进成长；无优惠券、无积分明细行
```

---

## 2. P0 体验问题

影响上线主任务完成，或点了像坏掉。

### P0-1 历史订单列表点了没反应 — PHASE-01 已加 toast

点卡片会 `uni.showToast('菜品明细请在本桌订单里查看')`，仍无详情页、不改 API。见 `orders.vue` `explainNoDetail`。

### P0-1（原文，已实施）

**分类：** A  
**问题：** 「我的订单」是任务 2 的终点，卡片展示了状态和金额，但 **没有点击**。用户会当详情入口去点，页面完全无反馈。  
**代码位置：** `subpkg-member/pages/orders.vue` L21–L32（`v-for` 的 `.record-card` 无 `@click`）。后端列表也不含 items（`ORDER_ENTRY_AUDIT.md`）。  
**用户影响：** 付完钱离开桌台后再来查「我点了什么」，只能看到金额和状态，点不开。会以为小程序坏了。  
**复现路径：** 登录 → 底栏「我的」→「我的订单」→ 点任意一张订单卡。  
**建议方向：** 最小改动二选一：卡片加 toast「菜品明细请在本桌订单里查看」；或产品拍板做只读详情（不在本审计实施）。不要把列表劫持回本桌弹层（会打乱已收口的实时/历史分流）。  
**是否需要产品决策：** 是。列表暂时当摘要，还是必须能看到菜名。

### P0-2 打烊或空菜单时，首页主卡可点但静默失败 — PHASE-01 已加 toast

`handleHomeStartOrder` 休息中 toast「门店休息中」，空菜单 toast「暂无菜品」；`handleFeaturedAdd` 同样有提示。仍不切 Tab、不加购。

### P0-2（原文，已实施）

**分类：** A  
**问题：** 按钮已写成「门店休息中 / 暂无菜品」，但整张 Hero 仍 `@click` 发出 `start-order`。处理函数直接 `return`，无 toast。  
**代码位置：** `HomeTab.vue` L13–L19；`useHistoryReorder.js` `handleHomeStartOrder` L32–L35。招牌「直接加入」同样：L53–L56 仍 emit，`handleFeaturedAdd` L37–L38 无提示。  
**用户影响：** 休息时段或菜单未配好时，用户按最大按钮，界面不动。  
**复现路径：** 店铺打烊或 `allDishes` 为空 → 底栏首页 → 点「立即点餐」或「开始点餐」。  
**建议方向：** 在 `handleHomeStartOrder` / `handleFeaturedAdd` 的 early return 里 `uni.showToast`（休息中 / 暂无菜品）。不要改业务流程。  
**是否需要产品决策：** 否。

---

## 3. P1 体验问题

建议优化，不挡扫码付钱。

### P1-1 首页主卡文案互相打架

**分类：** A  
**问题：** 同一张卡 kicker「今日推荐」、标题「立即点餐」、说明又是「共 N 道菜可点」（和上方状态卡重复）。用户分不清这是推荐还是入口。  
**代码位置：** `HomeTab.vue` L3–L20；`useHomeTabView.js` L17–L24。  
**用户影响：** 扫码后若切到首页，主动作仍找得到，但第一眼信息重复、语义叠。  
**复现路径：** 点餐页底栏第一个图标。  
**建议方向：** 只留一个主句（立即点餐）+ 一个状态（营业/可点道数）。「今日推荐」留给下面店长推荐。  
**是否需要产品决策：** 否（文案收敛）。

### P1-2 会员中心在 0 张券时仍说「您有 0 张优惠券可用」 — PHASE-02 已改标题

0 张时标题为「去点餐，结算自动用优惠」，按钮仍 emit `go-order`。

### P1-2（原文）

**分类：** A  
**问题：** 有 `bannerInfo` 就渲染主行动卡，文案写死「您有{{ couponCount }}张」。零张时像空承诺。  
**代码位置：** `MemberCard.vue` L51–L54。  
**用户影响：** 新会员点进会员 Tab，第一句是 0 张券，权益理解被带偏。  
**复现路径：** 登录且无可用券 → 底栏会员。  
**建议方向：** `couponCount === 0` 时改成「去点餐累积优惠」或隐藏这张卡，只留资产格。  
**是否需要产品决策：** 否。

### P1-3 「我的」没有积分、优惠券入口

**分类：** B  
**问题：** 积分和券只在会员 Tab。只走「我的」的人看不到。「积分」页规则还写去「我的优惠券」查看（`points.vue` L36），「我的」页却没有这一行。  
**代码位置：** `mine.vue` 服务列表 L97–L126；`MemberCard.vue` L39–L83；`points.vue` L33–L36。可见性审计已记。  
**用户影响：** 同一「查券/查积分」任务，从我的出发会以为没有。  
**复现路径：** 底栏我的 → 只看服务列表。  
**建议方向：** 在我的服务列表加两行，跳现有 `points.vue` / `coupon/list.vue`。不要新建页。  
**是否需要产品决策：** 否。

### P1-4 底栏四个图标无文字，且「我的」不是 Tab

**分类：** B  
**问题：** `BottomNav` 只有图标（L3–L16）。前三个切 `menu` 内 Tab，第四个 `navigateTo` 我的独立页（无底栏）。样式却四个完全一样。  
**代码位置：** `BottomNav.vue`；`menu.vue` `goMine` L670。  
**用户影响：** 第一次用可能点错（家/店/心）。进「我的」后底栏消失，只能微信返回。  
**复现路径：** 扫码进点餐 → 看底栏 → 点最右侧。  
**建议方向：** 四个图标下加「首页 / 点餐 / 会员 / 我的」短字（不是新组件）。「我的」保持独立页可以，但要让用户知道会离开点餐。  
**是否需要产品决策：** 加字可以不做决策；是否把我的改成页内 Tab 需要决策（不建议本轮做）。

### P1-5 优惠券 / 订单 / 积分 / 消费记录空态没有下一步按钮 — PHASE-02 已补订单与券可用 Tab

订单空态、优惠券「可用」空态已加 StateEmpty「去点餐」。积分/消费记录仍无按钮（审计未要求本阶段改）。

### P1-5（原文）

**分类：** A（空状态）  
**问题：** 说明了为什么空，但 StateEmpty 没 `actionText`，用户不能从空态去点餐。菜单空态反而有「重新加载」（`DishList.vue` L49–L54）。  
**代码位置：** `orders.vue` L16–L18；`consumptions.vue` L21–L22；`coupon/list.vue` L31–L34；`points.vue` L56–L57。  
**用户影响：** 空列表是终点，不像菜单空态能重试。  
**复现路径：** 新账号打开上述四页。  
**建议方向：** 给「暂无可用优惠券 / 暂无订单」加已有 StateEmpty 的 `actionText="去点餐"`，跳回 `menu` 点餐 Tab。已用/过期 Tab 可以不加。  
**是否需要产品决策：** 否。

### P1-6 「消费记录」和「我的订单」长得很像，职责不清

**分类：** B  
**问题：** 两页都是绿头 + 左文案右金额卡，且消费卡同样不可点。订单是堂食单；消费是入账/核销流水。用户很难分。  
**代码位置：** `orders.vue`；`consumptions.vue`；`mine.vue` L100–L116 两行文案。  
**用户影响：** 点错入口；消费记录也点了没反应。  
**复现路径：** 我的 → 对比「我的订单」和「消费记录」。  
**建议方向：** 文案写清「堂食订单」vs「核销/入账流水」。消费卡保持不可点可以，但不要看起来像订单详情。  
**是否需要产品决策：** 是（这两份列表对顾客是否都要露出）。

### P1-7 会员 Tab 加载失败不像订单页的 StateError

**分类：** A  
**问题：** `bannerInfo` 空但已登录时，自定义空页「普通会员」+「重新加载」，不是 StateError，也没说失败原因。  
**代码位置：** `MemberCard.vue` L86–L93。  
**用户影响：** 网络失败时不像「加载失败」，像权益只有「普通会员」。  
**复现路径：** 登录后会员接口失败 → 会员 Tab。  
**建议方向：** `memberLoading` 失败走已有 `StateError`（与订单/券列表一致）。  
**是否需要产品决策：** 否。

### P1-8 成功页赠券与「我的」券包没有连上

**分类：** B  
**问题：** 成功页可展示本单赠券和提醒订阅；`menu.vue` 已有 `goCoupons`（L1236–L1238）跳券列表，**模板未接到** PaymentSuccessSheet。产品冻结的三按钮也不含「去看券」。  
**代码位置：** `PaymentSuccessSheet.vue` L31–L46、L74–L83；`menu.vue` L1236。  
**用户影响：** 刚拿到券，不知道去会员 Tab 的「优惠券」看。不挡「关闭并等待」。  
**复现路径：** 支付成功且 `earnedCoupon` 有值。  
**建议方向：** 不要改三按钮层级（已冻结）。可在赠券卡上用现有「提醒我」；或成功关闭后 toast 提到会员中心。接 `goCoupons` 要产品点头。  
**是否需要产品决策：** 是（会不会变成第四按钮）。

---

## 4. P2 体验问题

长期，不挡上线。

### P2-1 CartBar / Checkout / 成功主按钮缺少 `.tap-shrink`

**分类：** C  
**问题：** 公共点击类在券条、我的按钮上有；CartBar「去结算」、Checkout 提交、成功主按钮没有。加购有脉冲和震动（`useCartFeedback.js`）。  
**代码位置：** `CartBar.vue` L26–L33；`CheckoutSheet.vue` L95；`PaymentSuccessSheet.vue` L75。  
**用户影响：** 手感偏「点了没按下去」。开 sheet / 出 toast 仍有结果反馈。  
**复现路径：** 点餐 Tab 点「去结算」。  
**建议方向：** 仅给 Checkout / Success 加已有 `.tap-shrink`。CartBar 视觉合同禁止改条和胶囊形态，按压缩放也算动视觉，不要顺手改 CartBar。  
**是否需要产品决策：** 否。CartBar 不要动。

### P2-2 首页状态与菜单头两套营业徽章

**分类：** C  
**问题：** HomeTab 胶囊「营业中/休息中」；ShopHeader 小方「营业中/已打烊」，色和圆角都不同。  
**代码位置：** `HomeTab.vue` L8–L10、L201–L203；`ShopHeader.vue` L11–L13、L127–L141。  
**用户影响：** 来回切 Tab 时状态看起来不像同一套。  
**复现路径：** 首页 vs 点餐头。  
**建议方向：** 不新增 token。下次 TOUCH 头时把颜色落到 `--brand` / `--text-3`。  
**是否需要产品决策：** 否。

### P2-3 成功页 / HomeTab 死 CSS

**分类：** D（顺带 C）  
**问题：** 成功页前半居中规则、HomeTab 第一套 badge 色被后写覆盖。不影响运行，后续改按钮容易改错套。  
**代码位置：** `PaymentSuccessSheet.vue` L132–L148 vs L326+；`HomeTab.vue` L121–L129 vs L187–L203。  
**用户影响：** 无直接感知。  
**复现路径：** 读源码。  
**建议方向：** TOUCH 这些文件时删失效规则。产品形态已冻结为底部 Sheet。  
**是否需要产品决策：** 否。

### P2-4 结算行价用 `toFixed(2)`，菜卡用 `formatPrice`

**分类：** D / C  
**问题：** 金额格式两套。PHASE-03 已列为可静默采用。  
**代码位置：** `CheckoutSheet.vue` L29、L45、L80、L89。  
**用户影响：** 极端金额才看得出。  
**建议方向：** 改走已有 `formatPrice`，不改 CTA。  
**是否需要产品决策：** 否。

---

## 5. 已符合规范部分

- **扫码点餐主链完整：** 默认落在点餐 Tab；CartBar 只开确认单（`CARTBAR_VISUAL_CONTRACT.md`）；Checkout 才支付；成功页三按钮与「关闭并等待」主路径已冻结。
- **确认单不是第二菜单：** Checkout 是 BaseSheet，符合产品规则。
- **实时 vs 历史订单已收口：** 成功页/气泡 = 本桌；我的订单/最近订单卡片 = `orders.vue`（`mine.vue` L81、L518–L525）。
- **菜单空/错分开：** 骨架 `LoadingStates`；失败 `StateError`「菜单加载失败」；空 `StateEmpty`「暂无菜品」+ 重新加载。
- **会员/券/积分/成长/消费** 页级加载、失败、空大多走 State*。
- **加购有反馈：** 数量脉冲、角标、震动（`useCartFeedback.js`）；再来一单有 toast。
- **成功页不允许点遮罩关闭**（`PAYMENT_SUCCESS_OVERLAY_DECISION.md`）。
- **券红金、会员等级色** 未并进品牌绿（Constitution）。

---

## 6. 不建议修改部分

| 项 | 原因 |
|---|---|
| CartBar 深色 / 92rpx 胶囊 / z-index 320 | 视觉合同已钉死；本审计禁止改 |
| 成功页迁 BaseSheet、点遮罩关闭、改成独立路由 | overlay 产品合同禁止 |
| 把「我的订单」点进本桌弹层 | 会打乱实时/历史分流 |
| 新建 AppButton / 统一 CTA 高度 / 扩 PriceText 档 | Design System Deferred；PHASE-03 已说明不是漏用 |
| 大规模改 BottomNav 成微信原生 tabBar | 超出体验打磨，等于改 IA |
| 消费详情页、旧 `card.vue`、核销码页 | 孤儿页，接上等于新功能，不是 polish |
| `goCoupons` 当成功页第四主按钮 | 会改冻结的三按钮层级 |

---

## 任务链路摘要

**任务 1 扫码点餐：** 链不断。下一步在点餐 Tab + CartBar「去结算」是清楚的。断层：打烊/空菜单首页静默点击（P0-2）；成功后心理路径符合「留下等待」。重复入口：首页「立即点餐」和底栏店图标都去点餐，可接受。无反馈：空车点「去结算」disabled 无 toast，可接受（按钮已灰）。

**任务 2 查看订单：** 入口已分实时/历史。体验洞：历史列表不能点（P0-1）；最近订单和「我的订单」现在进同一页，不再误开本桌。消费记录易混（P1-6）。

**任务 3 会员：** 会员 Tab 能到成长/积分/券。权益在成长页有网格。洞：0 张券文案（P1-2）；我的页缺入口（P1-3）；券/积分空态没下一步（P1-5）；失败态不像错误（P1-7）。不是空白页，是弱引导。
