# Admin 前端下一优先级审计（Phase-06）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-06
STATUS=ADMIN_EXPERIENCE_NEXT_PRIORITY_AUDIT
MODE=AUDIT_ONLY
PHASE_TYPE=CROSS_SYSTEM_PRIORITY_DECISION
BUSINESS_CODE_CHANGED=NO
SECURITY_GATE=PASS
```

本报告是同一份 `ADMIN_FRONTEND_SYSTEM_PHASE06_NEXT_PRIORITY_AUDIT.md` 的**完整版**。它此前在 `SECURITY_PREFLIGHT` 阶段中止（发现 `CustomerList.vue` 把原始 Bearer Token 写入 `sessionStorage`），该问题已由独立的 [Phase-06-SEC](./ADMIN_FRONTEND_SYSTEM_PHASE06_SEC_CUSTOMER_CONTEXT_CREDENTIAL_REMEDIATION.md) 修复并验证（commit `d5b986b`）。本次在 `SECURITY_GATE=PASS` 的前提下，从头执行完整的体验优先级审计——不复用旧版本里从未真正跑过的结论。

---

## 0. Baseline

```text
BASELINE_SHA = d5b986b97a81f3a894b513b4869c734ef20f5a86
BRANCH = main
WORKTREE_STATUS =
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条独立工作线：admin 性能可观测性）
  ?? docs/frontend/ADMIN_PERFORMANCE_BASELINE.md
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 全程未删除、未 reset、未 clean、未 stash、未混入本阶段提交，也未被本阶段的性能相关结论引用（见第 9 节）。

---

## 1. Security Gate Status

```text
SECURITY_PREFLIGHT_STATUS=PASS
SECURITY_REMEDIATION_COMMIT=d5b986b
RAW_ACCESS_TOKEN_PERSISTED_IN_CUSTOMER_CONTEXT=NO
TOKEN_DERIVED_VALUE_PERSISTED=NO
```

已在当前 HEAD 重新核实（不是复用历史结论）：`admin-h5/src/views/CustomerList.vue` 的 `currentContextIdentity()` 只返回 `localStorage.getItem('tenant_id') || ''`（[CustomerList.vue:158-160](../../admin-h5/src/views/CustomerList.vue)），文件内 `grep "localStorage.getItem('token')"` 零匹配；`admin-h5/src/stores/auth.js` 的 `clearAuth()` 含 `sessionStorage.removeItem('admin_customer_list_context')`。按规则不重新执行 Phase-06-SEC，直接进入体验优先级审计。

---

## 2. Current Admin Frontend Baseline

- **可信（Phase-03A~E）**：订单/Dashboard/菜品/会员/营销五个高频面的 loading/empty/error/success/unknown 状态真实性问题已收口。
- **一致（Phase-04）**：19→现在 20 个页面共用 `PageHeader`；9 个零消费者组件已删除；Ant 为主、Vant 为历史兼容的框架治理已建立。
- **高频效率（Phase-05A~C）**：OrderManage 新订单高亮、拒单二次确认；MenuManage 菜品名称搜索；CustomerList 详情往返上下文保持——均已实施。
- **安全（Phase-06-SEC）**：CustomerList 的会话上下文不再持久化任何凭证或凭证衍生值。

这四层工作没有覆盖：**Settings/表单类页面**（`StaffManage`/`MerchantSettings`/`settings/*` 共 10 个文件）此前没有被任何阶段触碰过；**视觉系统在深色模式下的实际合规性**也从未被验证过（暗色模式基础设施本身是在这些阶段之外独立建成的，见第 6 节）。这是本阶段发现的两个此前完全空白的区域。

---

## 3. Audit Method

```text
E1=CURRENT_CODE_EVIDENCE   当前真实源码直接证明
E2=CURRENT_RUNTIME_EVIDENCE 当前真实页面/浏览器/staging 证明
E3=HISTORICAL_AUDIT_EVIDENCE 历史报告存在，未重新验证
E4=PRODUCT_INFERENCE       产品推断
E5=ASSUMPTION              假设
```

`BROWSER_AUDIT=NOT_RUN`。`AUTHENTICATED=N/A`。`VIEWPORTS=N/A`（静态推理覆盖 ~390px 场景，未真实缩放浏览器验证）。`LIMITATIONS=` 本机没有可安全用于本次审计的登录态（生产商户账号不适合用来做视觉/响应式探索性截图；另有一条独立在建的 admin 性能压测本地环境，属于不相关 WIP，未借用，以免与另一条工作线产生状态冲突）。本阶段全部结论 `EVIDENCE_LEVEL=E1`：直接读取当前 HEAD 的 12 个视图文件 + 2 个共享组件 + 路由/Shell/全局样式表，逐行核实，不采信任何未重新验证的历史结论。

**审计执行方式**：用 4 个只读子代理并行审计，按页面分组（而非按维度分组，避免同一文件被读 4 遍）：① Dashboard+OrderManage、② MenuManage+CustomerList、③ CouponCenter+MarketingEffectiveness+CouponRecords、④ StaffManage+MerchantSettings+BusinessSettings+DeviceSettings+PaymentSettings（Settings/表单抽样）。每个子代理对分到的每个文件在四个维度（A/B/C/D）各自产出结构化结果，本节及以下各节是对四份独立报告的交叉核实与综合，多处发现被 2 个及以上独立子代理在不同文件里各自命中同一模式（见第 10 节），这本身就是 PATTERN/SYSTEMIC 而非巧合的强证据。

---

## 4. Information Hierarchy Audit（A）

覆盖全部 12 个文件。核心发现不是"信息缺失"，而是**动作视觉权重与其后果不匹配**，且这个模式反复出现：

| PAGE | HIERARCHY_GAP | SEVERITY | EVIDENCE |
| --- | --- | --- | --- |
| OrderManage.vue | 拒单 / 补打小票 / 退款 三个后果完全不同的动作共用同一套 `order-action-btn--reject` 危险红样式、同尺寸、同一行 | P1 | [OrderManage.vue:205,210-211,389,395-396,1793-1811](../../admin-h5/src/views/OrderManage.vue) |
| Dashboard.vue | 营业开关（停止接单）是与设置齿轮同权重的小徽章，无确认、无 loading 态 | P1 | [Dashboard.vue:11-18,363-373](../../admin-h5/src/views/Dashboard.vue) |
| CouponRecords.vue | "收回这张券"（不可逆）与"查看客户"（安全导航）同尺寸同权重 | P1 | [CouponRecords.vue:87-102](../../admin-h5/src/views/CouponRecords.vue) |
| PaymentSettings.vue | 全表单唯一的资金相关保存按钮是 `size="small"`，比 BusinessSettings/DeviceSettings 的低风险保存按钮视觉权重更低 | P1 | [PaymentSettings.vue:22](../../admin-h5/src/views/settings/PaymentSettings.vue) |
| CustomerList.vue | 会员总数只出现在列表底部分页脚注，PageHeader 没有副标题 | P2 | [CustomerList.vue:3-5,83-88](../../admin-h5/src/views/CustomerList.vue) |
| MarketingEffectiveness.vue | 5 列指标同字重同颜色，0% 核销率和 80% 核销率视觉上毫无区别 | P2 | [MarketingEffectiveness.vue:238-242](../../admin-h5/src/views/MarketingEffectiveness.vue) |
| MenuManage.vue | 售罄/一键恢复的异常发现与处理已经做得很好（一键 CTA 直接出现在首屏） | 正向发现，非缺陷 | [MenuManage.vue:37-41](../../admin-h5/src/views/MenuManage.vue) |

```text
INFORMATION_HIERARCHY_SCORE=68/100
SYSTEMIC_LEVEL=PATTERN（"危险动作与安全动作同权重"这一具体模式在 4 个文件独立出现，但多数单点严重度是 P1/P2，没有 P0）
```

## 5. Responsive / Mobile Audit（B）

`admin-h5` 的 Shell（`Layout.vue` + `App.vue` + `TabBar.vue`）是纯移动端单列布局，固定底部 TabBar，**没有桌面侧边栏，没有基于宽度的布局切换**——这不是缺陷，是这个产品从第一天就有的既定设计（Phase-01 §4.4 已写明"移动端一屏优先"）。

对 12 个文件的静态复核（零匹配 `@media` 的文件：Dashboard/OrderManage/MenuManage/CustomerList/MarketingEffectiveness——即全部 4 个 P0/P1 高频页 + 一个营销页）：

```text
PAGE=Dashboard.vue          PRIMARY_JOB_COMPLETABLE=YES  HORIZONTAL_OVERFLOW_RISK=NO   LAYOUT_FAILURE=NONE_FOUND
PAGE=OrderManage.vue        PRIMARY_JOB_COMPLETABLE=YES  HORIZONTAL_OVERFLOW_RISK=NO   LAYOUT_FAILURE=NONE_FOUND（grid auto-fill(minmax) 自适应；Modal/Drawer 依赖 Ant Design Vue 自带的 @media(max-width:screenSMMax) 响应式规则，非页面自建）
PAGE=MenuManage.vue         PRIMARY_JOB_COMPLETABLE=YES（列表）/ PARTIAL（表单内 80x80 固定图片框在 6/24 栅格列里偏紧，未证实溢出）
PAGE=CustomerList.vue       PRIMARY_JOB_COMPLETABLE=YES  HORIZONTAL_OVERFLOW_RISK=NO
PAGE=MarketingEffectiveness.vue  PRIMARY_JOB_COMPLETABLE=PARTIAL（5 列密集数据表在 ~390px 下每列仅约 62px，双行 caption+数字进一步挤压，无截断/滚动兜底）
PAGE=CouponRecords.vue      现有 @media(min-width:768px) 断点实际只做桌面居中，对窄屏风险区（4 列汇总格/2 列筛选）无覆盖，但未证实真的溢出
PAGE=DeviceSettings.vue     现有 @media(max-width:390px) 断点范围精准（只改 3 按钮行），其余 2 列区域评估为合理
```

真实发现是**触控目标尺寸**，而不是断点覆盖：OrderManage 头部按钮 28px 高、MenuManage 三个图标按钮仅 2px 间距、CustomerList/StaffManage 的小号按钮均低于常见 44px 触控指引——但这个问题与视口宽度无关（在任何宽度下都一样小），因此更准确地归入第 7 节 Usability，不归入 Responsive 本身。

```text
PROVEN_MOBILE_USAGE=UNKNOWN（无真实设备/埋点数据）
RESPONSIVE_MOBILE_SCORE=74/100
SYSTEMIC_LEVEL=LOCAL（MarketingEffectiveness 的密集表格是本次唯一有实质根据的收窄风险，其余文件均评估为静态合理，不构成系统性响应式缺陷）
```

## 6. Visual System Audit（C）

`admin-h5/src/styles/global.scss` 已经建立了一套相对成熟的 token 系统（`--brand`/`--text-1/2/3`/`--bg-page`/`--bg-card`/`--radius-card`），并在 `:root` 之外用 `@media (prefers-color-scheme: dark)` 整体翻转（[global.scss:4-40](../../admin-h5/src/styles/global.scss)）；`App.vue` 进一步同步 Ant Design Vue 自身的 `theme.darkAlgorithm`（[App.vue:20-31](../../admin-h5/src/App.vue)），并明确注释"跟随系统深浅色...两边同一个媒体查询条件，不会不同步"（App.vue:20-23 附近注释）。**这是一个已经建成、已经声明"会保持同步"的能力，不是本阶段建议新建的能力。**

对这个已声明的合同做逐文件复核，发现真实、可证明、影响理解（不是纯装饰）的违约：

| 位置 | 问题 | 后果 | 级别 |
| --- | --- | --- | --- |
| [PageHeader.vue:29-37](../../admin-h5/src/components/PageHeader.vue) | `background:#fff`、`border-bottom:#f0f0f0`、`color:#111` 全部硬编码，零 `var(--token)` | 这是 20 个页面共用的 `sticky` 顶栏（`grep "PageHeader"` 在 `views/` 下命中 20 个文件），深色模式下页面主体已翻黑，头部条会保持刺眼的白底黑字，"我在哪个页面"这条最基础信息的呈现载体本身失控 | **P0（系统性）** |
| [OrderManage.vue:1747-1752](../../admin-h5/src/views/OrderManage.vue) | 订单卡片"菜名"文字硬编码 `#111827`，卡片背景正确使用 `var(--bg-card)`（会翻深） | 文件自己的注释（OrderManage.vue:1734-1736）承认菜名是"这个页面使用频率最高、最需要一眼看清的信息"；深色模式下这行字会退化成近黑背景上的近黑文字 | **P0（单页但是最高频页 + 最高优先级信息）** |
| [CouponRecords.vue:486-494 vs 520-534](../../admin-h5/src/views/CouponRecords.vue) | 优惠券信息卡片背景硬编码 `#fff8ef`（奶油色），文字色用 `var(--text-1)`/`var(--text-2)`（会翻浅） | 深色模式下变成浅底浅字，对比度直接失败 | P1 |
| [MarketingEffectiveness.vue:178-187](../../admin-h5/src/views/MarketingEffectiveness.vue) | 窗口切换 tab 背景硬编码 `#fff`，激活态正确用 token | 深色模式下未激活的 tab 停留在硬编码白底 | P2 |
| [Dashboard.vue:558-569](../../admin-h5/src/views/Dashboard.vue) | 营业开关徽章样式与普通状态标签同权重，无危险色处理 | 与第 4 节的信息层级发现是同一处代码的两个侧面 | P2 |

**广度核实**：对 `src/views` + `src/components` 做了一次粗粒度扫描（`grep` 匹配 `color:#fff/111/000/333` 或 `background:#fff` 字面量，未逐一验证每处是否真的在深色模式下失效），命中 **30 个文件**，其中包括 4 个已被 Phase-02 认定为"已证明的 Level 2 共享组件"（`AssistedOrderSheet`/`InsightCard`/`PickupNoPicker`/`WorkbenchSyncBar`，连同 `PageHeader` 共 5 个）。这个扫描结果**不作为已证明缺陷计入优先级评分**（很多命中可能是渐变卡片上的白字这类无论主题都成立的合理用法），只作为"上表 5 处具体验证过的问题不是孤例"的规模佐证，标记为 E1（扫描本身是真实的）+ E4（"这意味着还有更多"是推断，未逐一验证）。

区分 FUNCTIONAL vs DECORATIVE：上表 5 项全部是 FUNCTIONAL_VISUAL_GAP（影响可读性/一致性判断），不是圆角、阴影这类装饰性差异；本次审计中确实发现的纯装饰性差异（如 `CouponCenter.vue` 的 hero 渐变硬编码色值、`BusinessSettings.vue` 用红色表示"休息日"的语义轻微错位）**未计入 P0/P1**，按规则处理。

Ant/Vant 混用核实：`CouponCenter`/`MarketingEffectiveness`/`CouponRecords` 自身代码只用 Vant，`OrderManage`/`MenuManage`/`CustomerList`/全部 Settings 页只用 Ant——但因为全部经由 `PageHeader`（纯 Ant 实现），几乎每个页面在运行时都是 Ant+Vant 混合渲染，这是既有架构（Constitution 已承认框架并存），不是新发现的违规。

```text
VISUAL_SYSTEM_SCORE=61/100
SYSTEMIC_LEVEL=SYSTEMIC（PageHeader 覆盖 20 个页面，含最高频的 OrderManage 在内的多个高频页面各自独立出现同类硬编码，且违反的是代码自己已经声明并部分实现的暗色模式合同，不是本阶段新提出的标准）
TOP_VISUAL_GAPS=PageHeader.vue 硬编码色值（系统性）、OrderManage.vue 菜名文字硬编码（单页最高优先级信息）、CouponRecords.vue 卡片背景/文字色反相冲突
```

## 7. Usability / Accessibility Audit（D）

已排除 Phase-03/05 覆盖过的内容（订单/菜品/会员/营销的 loading/empty/error 状态真实性、OrderManage 拒单确认、菜品名称搜索）。真实、未被覆盖过的发现：

**7.1 Settings 表单的状态真实性缺口（Phase-03 从未覆盖这个面）**

`BusinessSettings.vue`（营业开关/堂食/自提/外卖开关/配送费）和 `PaymentSettings.vue`（收款模式）都是"点击即乐观更新本地状态 → 异步保存 → 失败只弹 toast，不回滚"：

- [BusinessSettings.vue:14,22,26,30,164-170](../../admin-h5/src/views/settings/BusinessSettings.vue)：`v-model:checked` 直接绑定到同时也是保存 payload 的 `opSettings`，`saveOpSettings()` 失败分支只有 `message.error(...)`，`opSettings.value` 从未被复位。
- [PaymentSettings.vue:24,79-94](../../admin-h5/src/views/settings/PaymentSettings.vue)：同一模式，且这是全表单唯一处理"怎么收钱"的开关，`savePaymentMode()` 失败时 `paymentMode.value` 不回滚，`currentModeTip` 会继续显示保存失败的那个模式，toast 消失后页面上没有任何持续可见的失败信号。

这正是 Constitution §4 明确禁止的模式（"保存失败仍保持已保存外观"），只是发生在从未被 Phase-03 触碰过的 Settings 面，不是重复审计,是把已经确立的规则应用到一个此前的盲区。**该发现单点严重度高（P0/P1 候选），但覆盖面窄（本次抽样 5 个文件里 2 个命中）**，见第 13/16 节的处理方式。

**7.2 无二次确认的高风险动作 vs 已有的正确先例并存**

`DeviceSettings.vue` 的"重置密钥"正确使用了带后果说明的 `Modal.confirm`（[DeviceSettings.vue:221-231](../../admin-h5/src/views/settings/DeviceSettings.vue)），是本次抽样里唯一的最佳实践范例；但 `StaffManage.vue` 的员工角色变更（[StaffManage.vue:230-238](../../admin-h5/src/views/StaffManage.vue)）和 `PaymentSettings.vue` 的收款模式变更都没有对应的确认步骤——同一个仓库里已经有正确的先例，只是没有被套用到风险更高的两处。

**7.3 表单校验全部依赖全局 toast，无就近内联错误**

抽样的 5 个 Settings 文件里，**全部 5 个**都没有使用 Ant Design Vue 自带的 `:rules`/`validateStatus` 机制，"必填"标记（仅 `StaffManage.vue` 有）是纯装饰性星号，真正的校验是保存时用命令式 JS 判断再弹全局 toast。5/5 是本次审计里覆盖面最宽的单一模式。

**7.4 双提交防护缺口（分散但反复出现）**

`MenuManage.vue` 的 `toggleSoldOut`/`toggleCategory`（[MenuManage.vue:835-844,894-902](../../admin-h5/src/views/MenuManage.vue)，这是全应用点击频率最高的动作之一）、`CustomerList.vue` 的停用/恢复确认弹窗内的实际请求、`CouponRecords.vue` 的 `recallCoupon()`、`Dashboard.vue` 的 `toggleOpen`——均缺少请求进行中的 loading/disabled 防护，快速二次点击可能触发重复请求。

```text
USABILITY_ACCESSIBILITY_SCORE=63/100
SYSTEMIC_LEVEL=PATTERN（7.3 全局 toast-only 校验是 5/5 文件的真实 PATTERN；7.1 状态真实性缺口证据最强但只在 2/5 文件命中，覆盖面不够宽到 SYSTEMIC；7.4 分散在 4+ 个文件但每处单独看是局部）
```

无法从静态代码判断键盘可达性/焦点管理是否合规，本节全程未做 WCAG 合规声明，只如实记录"未发现自定义 focus 样式"这类事实（例如 `CustomerList.vue`/`MenuManage.vue`/`CouponCenter.vue` 均未在其 `<style>` 块内定义任何 `:focus` 规则，完全依赖 Ant/Vant/浏览器默认值——未验证是否足够）。

## 8. Already Solved Filter

```text
ALREADY_SOLVED=
  OrderManage 新订单发现              Phase-05A   SOLVED（本次 4 个子代理均未在 isHighlighted/highlight 相关代码路径发现回归）
  OrderManage 拒单误触                Phase-05A   SOLVED（Modal.confirm 结构确认仍在，OrderManage.vue:205 一带）
  MenuManage 菜品名称查找             Phase-05B   SOLVED（filteredCategories 跨分类搜索确认仍在）
  CustomerList 详情返回状态丢失        Phase-05C   SOLVED
  CustomerList credential persistence Phase-06-SEC SOLVED（本报告第 1 节重新核实）
  MenuManage Error 假 Empty           Phase-03C   SOLVED（本次审计未在错误处理路径发现回归）
  Marketing 假运行中                  Phase-03E   SOLVED
```

未发现以上任一项在当前 HEAD 出现回归，本阶段未将其中任何一项重新计入优先级评分。

## 9. Performance Boundary

```text
PERFORMANCE_PRIORITY=NOT_MAINLINE
```

本次 4 个子代理的静态审计过程中未发现"因加载/DOM/bundle 导致核心 Job 不可完成"的直接证据（`OrderManage.vue` 2005 行、`MenuManage.vue` 1608 行属于超大文件，Phase-01 已记录为已知问题，但这是可维护性问题，不是本次审计发现的新性能证据）。本阶段未新增性能埋点、未增加采样、未建设性能基础设施，也未借用仓库里正在独立进行的 admin 性能可观测性 WIP（见第 0 节，未触碰、未引用其结论）。

## 10. Systemic Issue Inventory

| ISSUE_ID | AREA | PAGE(S) | PROBLEM | SYSTEMIC_LEVEL | SEVERITY | EVIDENCE |
| --- | --- | --- | --- | --- | --- | --- |
| I-01 | C | PageHeader.vue（20 页共用） | 硬编码 #fff/#111/#f0f0f0，深色模式下顶栏不翻转 | **SYSTEMIC** | P0 | E1 |
| I-02 | C | OrderManage.vue | 菜名文字硬编码 #111827，卡片背景会翻深 | PATTERN（单文件但最高频页+最高优先级信息） | P0 | E1 |
| I-03 | C | CouponRecords.vue | 优惠券卡片背景硬编码、文字色走 token，深色模式对比度失败 | LOCAL | P1 | E1 |
| I-04 | D | BusinessSettings.vue, PaymentSettings.vue | 乐观本地更新 + 保存失败不回滚，无持续可见失败信号 | PATTERN（2/5 抽样命中，含全应用唯一收款模式开关） | P0（PaymentSettings）/ P1（BusinessSettings） | E1 |
| I-05 | D | 全部 5 个 Settings 抽样文件 | 表单校验只有全局 toast，无内联字段错误，"必填"星号大多装饰性 | **PATTERN（5/5）** | P1 | E1 |
| I-06 | A/C | OrderManage.vue | 拒单/补打小票/退款 同权重同色 | PATTERN | P1 | E1 |
| I-07 | A/D | Dashboard.vue | 营业开关无确认、无 loading，与设置按钮同权重 | LOCAL | P1 | E1 |
| I-08 | A/D | CouponRecords.vue | "收回这张券"与"查看客户"同权重；recallCoupon 无双提交防护 | LOCAL | P1 | E1 |
| I-09 | A | PaymentSettings.vue | 全表单最高风险的保存按钮反而是 size="small" | LOCAL | P1 | E1 |
| I-10 | D | MenuManage.vue | toggleSoldOut/toggleCategory 无双提交防护（全应用最高频动作之一） | LOCAL | P1 | E1 |
| I-11 | D | StaffManage.vue, PaymentSettings.vue | 高风险变更（角色/收款模式）无确认，而 DeviceSettings 的密钥重置有正确先例 | PATTERN | P1 | E1 |
| I-12 | B | MarketingEffectiveness.vue | 5 列密集数据表在 ~390px 下单列仅约 62px，无截断/滚动兜底 | LOCAL | P2 | E1 |
| I-13 | A | CustomerList.vue | 会员总数只在列表底部出现，PageHeader 无副标题 | LOCAL | P2 | E1 |
| I-14 | D | StaffManage.vue | 未使用共享 PageHeader，硬编码色值，游离于其余 4 个 Settings 页的模式之外 | LOCAL | P2 | E1 |

## 11. Priority Matrix

| 维度 | A 信息层级 | B 响应式 | C 视觉系统 | D 可用性 |
| --- | --- | --- | --- | --- |
| BUSINESS_IMPACT | 3 | 2 | 4 | 4 |
| USER_FREQUENCY | 4 | 3 | 5 | 3 |
| TASK_BLOCKING | 2 | 1 | 4 | 3 |
| SYSTEM_BREADTH | 3 | 2 | 5 | 4 |
| EVIDENCE_CONFIDENCE | 4 | 3 | 5 | 5 |
| IMPLEMENTATION_COST | 3 | 3 | 2 | 3 |
| REGRESSION_RISK | 2 | 2 | 2 | 3 |
| **VALUE_SCORE**（前 5 项相乘） | 288 | 36 | **2000** | 720 |

```text
A: WHY_NOW=危险动作视觉权重问题真实存在，但多数发现是 P1/P2，且与 C/D 的具体条目大量重叠（同一行代码常常同时是"层级问题"和"视觉/可用性问题"），独立成主线的边际价值有限
   WHY_NOT_NOW=没有独立于 C/D 之外、单独站得住的 SYSTEMIC 级证据
   TOP_EVIDENCE=OrderManage 三个危险动作同权重（E1）
   TOP_USER_IMPACT=中——影响判断成本，不影响任务能否完成
   SYSTEMIC_LEVEL=PATTERN

B: WHY_NOW=（无——本次审计的静态证据反而系统性地否定了"响应式是问题"这个假设）
   WHY_NOT_NOW=12 个文件里 11 个静态复核 PRIMARY_JOB_COMPLETABLE=YES 或有明确理由判定不构成溢出；4 个 P0/P1 高频页零 @media 但都靠 flex/grid 自适应或 Ant 组件自带响应式规则撑住，不是真空；唯一实质命中（MarketingEffectiveness 密集表格）是 LOCAL 单点，不是 SYSTEMIC；PROVEN_MOBILE_USAGE=UNKNOWN，没有真实使用数据支持"移动端是主要问题"这个论断
   TOP_EVIDENCE=MarketingEffectiveness 5 列表格窄屏挤压（E1，单点）
   TOP_USER_IMPACT=低——被审计的核心任务链均评估为可完成
   SYSTEMIC_LEVEL=LOCAL

C: WHY_NOW=PageHeader 覆盖 20 个页面，OrderManage 菜名硬编码发生在全应用最高频页面的最高优先级信息上；违反的是代码自己已经建成并声明"会保持同步"的暗色模式合同，不是本阶段新提出的标准；3 个独立子代理在互不知晓彼此发现的情况下各自命中同一类问题（PageHeader 硬编码），这是强 PATTERN/SYSTEMIC 信号；实施成本低（token 替换，机械、可写合同测试锁定），回归风险低
   WHY_NOT_NOW=（红队评审见第 12 节）
   TOP_EVIDENCE=PageHeader.vue:29-37（E1，20 个消费者）+ OrderManage.vue:1747-1752（E1，最高频页最高优先级信息）
   TOP_USER_IMPACT=高——在深色模式触发时是真实的理解能力丧失，不是偏好问题
   SYSTEMIC_LEVEL=SYSTEMIC

D: WHY_NOW=I-04（Settings 乐观更新不回滚）和 I-05（5/5 表单只有 toast 校验）都是真实、此前从未被审计过的盲区，I-04 单点业务后果甚至比 C 更重（收款模式说错就是真金白银）
   WHY_NOT_NOW=I-04 目前只在 2/5 抽样文件命中，还没有证据证明它是 SYSTEMIC（覆盖全部 Settings 面还是只是这 2 个）；D 类发现天然分散在很多不同页面的不同动作里，不像 C 有一个单一根因（token 合规）可以用一次性、低成本、可验证的方式收敛——D 更适合被当作独立的、聚焦的小步修复（类似 Phase-06-SEC 的处理方式），而不是一整个 Phase-06A 主题
   TOP_EVIDENCE=PaymentSettings.vue:79-94 保存失败不回滚（E1）
   TOP_USER_IMPACT=高但低频——收款模式配置本身很少被改动
   SYSTEMIC_LEVEL=PATTERN
```

## 12. Red-Team Review

排名第一候选：**VISUAL_SYSTEM**。反方质询：

> **真的影响老板完成工作吗，还是只是"不好看"？**
> 回应：上表 5 项全部标记为 FUNCTIONAL_VISUAL_GAP，不是圆角/阴影这类 DECORATIVE_GAP。最强的一条（OrderManage 菜名）直接命中文件自己代码注释里承认的"最需要一眼看清的信息"；PageHeader 的问题直接影响"我在哪个页面"这个信息层级的最基础一环。这不是审美判断，是"文字在深色背景上是否可读"这种二元、可验证的事实。

> **有没有证据老板真的在用暗色模式？**
> 回应：`PROVEN_DARK_MODE_USAGE=UNKNOWN`——如实标注，没有真实使用数据。但这个反问的前提本身站不住：暗色模式不是本阶段建议新投入的、尚未验证需求的能力，而是仓库里**已经建成、已经声明"两边同一个媒体查询条件，不会不同步"**（App.vue 注释原文）的既有合同。本阶段发现的是"这个已经做出的承诺，代码没有兑现"，性质上更接近一个功能不完整的 bug，而不是一次没有证据支撑的新体验投资。iOS/Android 的深色模式很大比例是跟随系统或定时自动切换（例如晚间自动开启），与餐厅老板高频使用后台的晚市时段存在合理重叠，但这一点本身是 E4 产品推断，不作为决策的必要支撑——即便忽略这层推断，"违反自建合同"这一点单独就足以成立。

> **桌面端是否存在更高价值的问题？**
> 回应：这个仓库从架构上就没有区分桌面/移动布局（Layout.vue 只有一个 TabBar 底栏 Shell），不存在"桌面端专属"的问题空间需要单独比较。

> **响应式改造是否会扩大到大量页面？**
> 回应：本次结论恰恰是不选 B（Responsive）为第一优先级，见第 11 节。

> **是不是因为窄屏截图最明显所以显得优先级高？**
> 回应：本次全程静态审计，没有截图、没有运行时渲染，排除了"视觉冲击力误导判断"这个风险来源本身。

```text
RED_TEAM_RESULT=SURVIVES
```

## 13. Top Priority

```text
TOP_PRIORITY_AREA=VISUAL_SYSTEM
TOP_PRIORITY_PROBLEM=深色模式 token 合规缺口——PageHeader（20 页共用的顶栏组件）与多个高频/次高频页面（OrderManage 菜名、CouponRecords 优惠券卡片、MarketingEffectiveness 窗口切换）硬编码颜色值，绕过了 global.scss 已经建成的 --token 系统，导致深色模式下真实出现"文字不可读"或"头部条不跟随主题"这类理解能力丧失，而不是纯粹的审美不一致
TOP_PRIORITY_USER=全体登录用户（老板/店长/前台/服务员/后厨）中开启了系统深色模式或系统按时间自动切换深色模式的部分——PageHeader 覆盖面是全部 20 个页面，不分角色
TOP_PRIORITY_JOB=打开任意页面时，能看清"我在哪、当前最关键的信息是什么"（PageHeader 标题、OrderManage 菜名等）
SYSTEMIC_LEVEL=SYSTEMIC
PRIMARY_EVIDENCE_LEVEL=E1
WHY_FIRST=覆盖面最广（20 个页面共用组件 + 独立命中最高频页面的最高优先级信息）、后果最直接可验证（可读性二元事实，非主观判断）、修复成本最低（token 替换是机械操作，可用一份"sessionStorage/输出内容不得包含硬编码色值字面量"式的静态合同测试锁定，不涉及交互逻辑或状态机改动）、回归风险最低（不改变任何业务逻辑），且不是本阶段新提出的标准——是让代码兑现自己已经声明的合同
WHY_NOT_OTHER_AREAS=见第 11/14 节
```

## 14. Why Not The Others

- **INFORMATION_HIERARCHY**：真实但价值分散——大部分发现（OrderManage 三危险动作同权重、Dashboard 营业开关、CouponRecords 收回券按钮）本质上是"视觉权重"或"缺少确认/loading"问题，分别与 C、D 的具体条目重叠，没有独立于两者之外、自成体系的 SYSTEMIC 证据链，适合作为 C/D 落地时顺带处理的具体条目（见第 16 节），不适合单独立项。
- **RESPONSIVE_MOBILE**：本次审计投入了与其它三个维度同等的静态复核精力，结论是这个假设**没有被证据支持**——4 个最高频页面零 `@media` 但都靠已有的 flex/grid/Ant 内置响应式撑住；唯一站得住的单点问题（MarketingEffectiveness 密集表格）是 LOCAL，不足以支撑一整个 Phase 的投入；且完全没有真实使用数据证明这是老板遇到的真实问题。
- **USABILITY_ACCESSIBILITY**：D 类发现里最重的一条（I-04，Settings 保存失败不回滚）单点业务后果甚至可能超过 C，但它的证据目前只覆盖 5 个抽样文件里的 2 个，还不构成 SYSTEMIC 级证据支撑一整个 Phase-06A 主题；且 D 类问题天然分散在各页各自不同的交互细节里（表单校验、双提交防护、确认步骤），根因不像 C 那样可以用一次性、低成本、可自动化验证的方式收敛。**明确建议**：I-04 不应该被"等 Phase-06A 结束后再排队"，其严重度和 Phase-06-SEC 处理安全发现时的紧迫度类似（真实、局部、修复成本低、业务后果具体），适合被单独提出为一个小范围修复任务，见第 16 节。

## 15. Phase-06A Definition（只定义，不实施）

```text
PHASE_06A=P0-ADMIN-FRONTEND-SYSTEM-PHASE-06A
STATUS=ADMIN_VISUAL_HIERARCHY
SCOPE_CANDIDATE=
  1. PageHeader.vue：#fff/#111/#f0f0f0 → var(--bg-card)/var(--text-1)/var(--border)（单文件，20 个页面自动受益，零业务逻辑改动）
  2. OrderManage.vue 菜名/数量文字：硬编码 hex → var(--text-1) 等对应 token（OrderManage.vue:1747-1758 一带）
  3. CouponRecords.vue 优惠券卡片背景：#fff8ef → 对应 token 或改为背景/文字同源
  4. MarketingEffectiveness.vue 窗口切换 tab：#fff → var(--bg-card)
  5. OrderManage.vue 本地 .tag-pending（#dc2626）与全局 global.scss 的 .tag-pending（#ef4444/var(--danger)）二选一收敛，消除同语义状态色漂移
VERIFICATION_APPROACH_CANDIDATE=为改动到的文件写一份静态合同测试：断言触摸范围内不再出现裸 hex 字面量用于文字色/背景色（允许渐变、品牌色等自洽场景的例外，需逐项列出并说明理由），而不是要求真实截图对比（本仓库没有 Vue 渲染测试框架，延续 Phase-03~06 一贯的源码结构断言 + 行为镜像方法论）
NOT_IN_SCOPE=不新增视觉 token、不做全站视觉改版、不触碰 Ant/Vant 框架选择、不改变任何业务逻辑/状态机/API
```

本阶段（Phase-06）到此为止不实施上述任何一条，Phase-06A 需要独立的实施任务和验收证据，且启动前需按 Touch And Migrate 重新确认触摸范围。

## 16. Deferred Backlog

不计入 Phase-06A 范围，但明确记录、不建议无限期搁置：

```text
BACKLOG-01（建议尽快单独立项，类似 Phase-06-SEC 的处理节奏）=
  I-04：BusinessSettings.vue / PaymentSettings.vue 保存失败不回滚，无持续可见失败信号
  理由：这是 Constitution §4 状态合同明确禁止的模式，出现在此前从未被 Phase-03 覆盖的 Settings 面；
  PaymentSettings 那一处涉及"怎么收钱"，业务后果具体，且修复成本低（补一个 revert-on-failure 分支）
  建议：不要等 Phase-06A（视觉）做完再排期，可作为独立小步任务提前处理

BACKLOG-02=
  I-05：5/5 抽样 Settings 表单只有全局 toast 校验，无内联字段错误
  理由：PATTERN 证据最强（5/5），但单点严重度是 P1 不是 P0，且需要的是引入 a-form :rules 这一更大范围的表单模式改造，成本高于 BACKLOG-01

BACKLOG-03=
  I-06/I-07/I-08/I-09：危险动作与安全动作视觉权重不匹配（OrderManage 拒单/补打/退款、Dashboard 营业开关、CouponRecords 收回券、PaymentSettings 保存按钮）
  理由：分散在多个页面，每处成本都不高，但没有一个能自动收敛其它几处的单一根因；适合在 Phase-06A 触摸对应文件时顺手迁移（Touch And Migrate 范围内），不需要单独立项

BACKLOG-04=
  I-10/I-11：双提交防护缺口（MenuManage 售罄/分类切换、CouponRecords 收回券）、高风险变更无确认（StaffManage 角色、PaymentSettings 模式）
  理由：与 BACKLOG-03 同类处理——分散、低成本、适合 Touch And Migrate 时顺手处理，不单独立项

BACKLOG-05=
  I-12：MarketingEffectiveness.vue 窄屏密集表格
  理由：LOCAL 单点，P2，不紧急

BACKLOG-06=
  I-14：StaffManage.vue 未使用共享 PageHeader、硬编码色值，游离于其余 4 个 Settings 页
  理由：P2，且如果 Phase-06A 触摸 PageHeader.vue 本身，顺带把 StaffManage 迁移到共享组件是自然的小步扩展
```

---

## ACCEPTANCE

1. **当前 Admin 下一块最大体验短板是什么？** 深色模式 token 合规缺口（视觉系统）——代码已经建成并声明的暗色模式合同，在 20 个页面共用的 `PageHeader` 和多个高频页面的核心信息上没有被兑现，导致真实的可读性失败，不是审美偏好问题。
2. **是否有 E1/E2 证据？** 有 E1，全部结论直接来自当前 HEAD 源码逐行核实，含跨 3 个独立子代理互不知晓彼此发现却各自命中同一 PageHeader 硬编码问题的交叉验证。没有 E2（未做浏览器运行时验证，见第 3 节 LIMITATIONS）。
3. **它是 Local / Pattern / Systemic？** SYSTEMIC——PageHeader 覆盖全部 20 个页面；OrderManage 菜名硬编码虽是单文件命中，但发生在全应用最高频页面的最高优先级信息上，与 PageHeader 问题共享同一根因（token 合规执行不一致）。
4. **Information Hierarchy 成熟度是多少？** 68/100，PATTERN 级别（危险动作视觉权重问题反复出现但多为 P1/P2，且与 C/D 大量重叠）。
5. **Responsive / Mobile 成熟度是多少？** 74/100，LOCAL 级别（唯一站得住的问题是 MarketingEffectiveness 一个文件；核心高频页均评估为可完成核心任务）。
6. **Visual System 成熟度是多少？** 61/100，SYSTEMIC 级别（本次审计最低分，也是唯一被判定为 SYSTEMIC 的维度）。
7. **Usability / Accessibility 成熟度是多少？** 63/100，PATTERN 级别（5/5 表单校验模式是最强的广度证据，但最高严重度单点集中在 2/5 文件）。
8. **是否剔除了 Phase-03~05 已解决问题？** 是，见第 8 节，逐项重新核实确认无回归，均未重新计入本阶段评分。
9. **是否没有重新把性能拉回主线？** 是，见第 9 节，`PERFORMANCE_PRIORITY=NOT_MAINLINE`，未新增埋点/采样/基础设施，未借用/引用独立的性能可观测性 WIP。
10. **是否区分移动端技术能力和真实使用数据？** 是，`PROVEN_MOBILE_USAGE=UNKNOWN` 和 `PROVEN_DARK_MODE_USAGE=UNKNOWN` 均如实标注，未编造真实用户行为数据；第 12 节红队评审明确处理了"暗色模式使用率未知"这个反问，说明结论不依赖于这个未知数。
11. **是否没有把装饰性问题判断成 P0？** 是，第 6 节明确区分 FUNCTIONAL_VISUAL_GAP 与 DECORATIVE_GAP，Top Priority 选定的 5 项全部是 FUNCTIONAL，装饰性差异（渐变硬编码色值、红色表示休息日的语义轻微错位等）均未计入 P0/P1。
12. **是否完成 Red-Team？** 是，见第 12 节，`RED_TEAM_RESULT=SURVIVES`，逐条回应了"是否只是不好看"“有没有真实暗色模式使用证据”“桌面端是否有更高价值问题”“响应式改造范围”“是否被截图视觉冲击力误导”五个质询。
13. **是否最终只选择一个方向？** 是，`TOP_PRIORITY_AREA=VISUAL_SYSTEM`，未选择"同时推进多条线"。
14. **是否明确为什么其它三个不是现在？** 是，见第 14 节，逐一说明 A/B/D 未入选的具体理由，其中 D 类最严重的单点发现（I-04）被明确建议不等 Phase-06A 结束、单独提前处理（第 16 节 BACKLOG-01）。
15. **Phase-06A 是否只包含一个问题域？** 是，见第 15 节，`STATUS=ADMIN_VISUAL_HIERARCHY`，范围候选全部是 token 合规收敛，未混入信息层级、响应式或可用性的独立改动（相关联的可用性/层级细节留在 BACKLOG-03/04，作为 Touch And Migrate 时的顺带项，不是 Phase-06A 的主线目标）。
16. **本阶段是否 Docs-Only？** 是，未修改 `admin-h5/src`、`saas-base`、`member-mini-client` 任何一行业务代码；只新增/更新本报告与两个索引文件。

```text
FINAL_DECISION=RESULT A: ADMIN_NEXT_EXPERIENCE_PRIORITY_READY
TOP_PRIORITY_AREA=VISUAL_SYSTEM
TOP_PRIORITY_PROBLEM=深色模式 token 合规缺口（PageHeader 等共享组件 + 多个高频页面核心信息硬编码颜色，未兑现代码自建的暗色模式合同）
SYSTEMIC_LEVEL=SYSTEMIC
PRIMARY_EVIDENCE_LEVEL=E1
PHASE_06A=P0-ADMIN-FRONTEND-SYSTEM-PHASE-06A ADMIN_VISUAL_HIERARCHY
BUSINESS_CODE_CHANGED=NO
SECURITY_GATE=PASS
```

## COMMIT_RULE

```text
CHANGED_FILES=
  docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE06_NEXT_PRIORITY_AUDIT.md（完整重写，原中止版本被完整版取代）
  PROJECT_INDEX.md
  PROJECT_KNOWLEDGE_MAP.md
STAGED_FILES=同上，仅这 3 个文件
UNRELATED_WIP_INCLUDED=NO
```

## NEXT_PHASE

推荐执行顺序：优先处理 `BACKLOG-01`（PaymentSettings/BusinessSettings 保存失败不回滚，独立小步任务，不依赖 Phase-06A），随后按第 15 节定义启动 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-06A ADMIN_VISUAL_HIERARCHY`（独立立项，需要自己的 TDD 证据和验收标准）。`BACKLOG-02~06` 不建议单独立项，留待相关页面下次被真实需求触摸时按 Touch And Migrate 顺带处理。
