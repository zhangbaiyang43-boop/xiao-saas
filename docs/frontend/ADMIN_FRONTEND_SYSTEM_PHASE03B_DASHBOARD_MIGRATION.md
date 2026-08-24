# Dashboard 经营视图 Touch And Migrate（Phase-03B）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03B
STATUS=DASHBOARD_BUSINESS_VIEW_MIGRATION
PREVIOUS_PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03A
REFERENCE=ADMIN_FRONTEND_CONSTITUTION.md V1.0, ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md, ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md
REPOSITORY_BASELINE_SHA=5aa289a9dbaab3389089b66e2971982ae0f0547d
SCOPE=admin-h5/src/views/Dashboard.vue（状态展示逻辑，1 处最小修改）
BUSINESS_CODE_CHANGE=YES（仅刷新反馈分支，见第 3/4 节）
API_CHANGE=NO
DATABASE_CHANGE=NO
NEW_METRIC=NO
NEW_FEATURE=NO
FULL_PAGE_REWRITE=NO
```

## 1. Dashboard Jobs 分析

沿用并落实 [ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md §2.2](./ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md) 已定义的 Dashboard Jobs：

- **用户**：老板 / 店长。
- **任务**：开店或巡店时，快速确认今天经营结果、当前异常、下一步动作。
- **成功标准**：老板打开后台后，能在数秒内完成三个判断——今天生意怎么样、有没有异常需要处理、下一步做什么——而不需要先读懂一屏图表。
- **核心动作**：处理待办、跳转异常来源。
- **禁止展示**：无法由真实数据证明的“运行中/正常”；与今日决策无关的历史趋势置顶。

老板打开首页不是来“看数据”的，是来做判断的。这意味着信息层级本身就是这个 Job 的一部分，不是可选的视觉优化：如果异常和结果混在一起、或者结果本身不可信（比如把接口失败显示成 0 元营业额），老板的判断就是错的，Job 没有被完成，无论页面看起来多整洁。

## 2. 当前问题审计

按 CURRENT_AUDIT 的五个检查点，逐条核对当前 `Dashboard.vue`（而不是复述历史结论）：

### 2.1 指标真实性

`loadStats()`（[Dashboard.vue:413](../../admin-h5/src/views/Dashboard.vue)）用 `Promise.all` 并行拉取经营统计和订单概况，`getDashboardStats().then(r => { if (r?.code !== 200 || !r.data) throw ... })` 拒绝非成功响应；只有整个 `Promise.all` resolve 后才 `statsError.value = false` 并写入 `overview`/`stats`/`memberPulse`；`catch` 分支只设 `statsError.value = true`，不写入任何字段。营业额字段 `todayRevenue: d.today_revenue || 0` 里的 `|| 0` 只在成功分支内部生效，兜底的是“响应体里这个字段缺失”，不是“请求失败”——两者已经分开处理。**结论：已符合，接口失败不会伪装成 0 营业额。**

### 2.2 Loading 状态

`statsLoaded = ref(false)` 初始为假，`StatCard`（[StatCard.vue:2-8](../../admin-h5/src/components/StatCard.vue)）模板顺序是 `v-if="loading"`（骨架屏）→ `v-else-if="error"`（错误文案 + 重试）→ `v-else`（真实数值），三者互斥。首屏在 `statsLoaded` 变真之前始终展示骨架屏，不会闪出 0 或空值。`InsightCard`（智能营销卡片）同样是 `v-if="loading"` 骨架屏 / `v-else` 渲染插槽，插槽内的 `marketingError`/`marketingEnabled` 三态判断只有在 `marketingLoaded` 变真之后才会被渲染，不存在“骨架屏消失但状态还没确定”的空窗期。**结论：已符合。**

### 2.3 Error 状态

`:error="statsError"` + `error-text="数据加载失败，请检查网络"` + `@retry="loadStats"`（[Dashboard.vue:65-69](../../admin-h5/src/views/Dashboard.vue)）已经把营收卡的失败态和重试入口接好；`StatCard` 内部 `v-else-if="error"` 优先于数值渲染分支，失败时不会显示任何数字。会员看板、近 7 天趋势、二单转化率、热销榜均包在 `v-if="!statsError"` 之外（[:74, :86, :91, :146](../../admin-h5/src/views/Dashboard.vue)），失败时整体不渲染而不是显示假数据；营销卡片有独立的 `marketingError` 三态（[:100-112](../../admin-h5/src/views/Dashboard.vue)）。**结论：已符合。**

### 2.4 Empty 状态

真实的“今天营业额是 0”不是错误，是事实——`statsError=false` 时 `StatCard` 直接渲染 `a-statistic :value="0"`，这就是正确行为，不需要额外的空态占位符掩盖真实的 0。近 7 天热销榜在 `statsLoaded` 且 `topDishRankItems.length===0`（新店还没有销量数据）时整块不渲染（[:146](../../admin-h5/src/views/Dashboard.vue)），符合 OPPO 原则里“正常系统状态静默”——这是一个低优先级辅助信息块，没有可操作的下一步，不渲染比渲染一句“暂无数据”更符合 Jobs（老板不需要为一个空榜单做任何决策）。**结论：已符合，无需改动。**

### 2.5 信息优先级

当前首屏顺序（模板从上到下）：Hero（营业状态开关）→ 套餐状态条（低强度，失败不渲染）→ 待办（`todoItems`，只在有异常/待处理时出现）→ 今日战报（StatCard）→ 会员看板 → 近 7 天趋势 → 二单转化率 → 智能营销 → 近 7 天热销榜 → 新商家引导。`todoItems` computed（[:276-319](../../admin-h5/src/views/Dashboard.vue)）只在有待接单、待结账、打印异常或桌台异常时才产出条目，正常时 `TransitionGroup` 不渲染任何内容，版面直接让给下面的结果类信息——这正是 CURRENT_PROBLEM_AUDIT 要求的“异常 > 结果 > 辅助信息”排序，且已经在代码里实现，不是文档层面的意图。**结论：已符合，异常优先于结果、结果优先于辅助信息的顺序已经成立，本阶段不需要调整信息层级。**

### 2.6 本次审计发现的唯一真实缺口：手动下拉刷新的失败反馈缺失

```js
// Before（本阶段发现的问题）
async function onPullRefresh() {
  await Promise.all([loadStats(), loadMarketingPreview(), loadSystemStatus(), loadTableCouponActivity(), loadSubscriptionStrip()])
  refreshing.value = false
  if (!statsError.value) message.success('已刷新')
}
```

`onPullRefresh` 在 `statsError` 为真时**没有任何反馈**——不报错、不提示，只是安静地收起下拉刷新动画。营收卡本身仍然会显示常驻的错误态（[StatCard.vue error 分支](../../admin-h5/src/components/StatCard.vue)），所以老板不会被误导为“已经是最新数据”，但这和 [ADMIN_FRONTEND_SYSTEM_PHASE03A_ORDER_STATE_MIGRATION.md](./ADMIN_FRONTEND_SYSTEM_PHASE03A_ORDER_STATE_MIGRATION.md) 里 `OrderManage.manualRefresh` 的既有合同不一致——那里失败会明确 `message.error('刷新失败，请检查网络后重试')`。同一个抽象事件（手动刷新失败）在两个页面上的反馈方式不一致，属于 Constitution §3.4“反馈 MUST 说明发生了什么”的一个小缺口，也是本阶段 TDD_REQUIREMENT 第 5 条明确要求覆盖的场景。**结论：不符合，本阶段修复。**

## 3. 修改方案

本阶段采用最小迁移：**只修改第 2.6 节发现的一处刷新反馈缺口，不触碰其余任何已经符合契约的逻辑。**

原因：

1. 第 2.1–2.5 节的五个检查点在当前源码中已经实现，继续“迁移”会违反 Constitution §7/§8 的 Touch And Migrate 原则（迁移必须以商家任务改善或风险降低为目的），也违反本阶段 STRICT_RULES 的“最小修改”“禁止为了统一而统一”。
2. 第 2.6 节是一个真实、具体、可验证的状态失真缺口——老板手动下拉刷新失败时得不到任何"失败"反馈，需要靠自己注意到营收卡片没有变化才能发现刷新其实失败了，这直接影响 Jobs 的成功标准（"3 秒内获得经营判断"要求刷新本身的结果也必须是可信的）。
3. 修复方式复用现有 `message` 机制和现有 `statsError` 信号，不引入新状态变量、不改变数据来源、不触碰 API。

修改本身：

```js
// After
async function onPullRefresh() {
  await Promise.all([loadStats(), loadMarketingPreview(), loadSystemStatus(), loadTableCouponActivity(), loadSubscriptionStrip()])
  refreshing.value = false
  if (statsError.value) message.error('刷新失败，请检查网络后重试')
  else message.success('已刷新')
}
```

文案与 `OrderManage.manualRefresh` 保持一致（"刷新失败，请检查网络后重试"），符合 Phase-02 规则里"同一抽象事件在不同页面保持一致语言"的隐含要求，不是新造一套文案。

## 4. 状态合同变化

| 状态 | Before | After |
| --- | --- | --- |
| 首次/轮询统计接口失败 | 已符合：`statsError` 为真，StatCard 显示 error 分支，其余区块整体不渲染 | 无变化 |
| 统计接口成功（含真实 0） | 已符合：真实数值原样展示，`statsError=false` | 无变化 |
| 空数据（新店无销量） | 已符合：低优先级榜单区块静默不渲染 | 无变化 |
| 局部模块失败（营销/打印机/桌台异常/套餐条） | 已符合：各自独立 error/unknown 状态，互不传染 | 无变化 |
| **手动下拉刷新失败** | **不符合：`refreshing=false` 后无任何提示，老板无法区分"已刷新且成功"和"刷新完成但失败"** | **符合：`statsError` 为真时 `message.error('刷新失败，请检查网络后重试')`，为假时才 `message.success('已刷新')`** |

**净变化**：1 行代码从 `if (!statsError.value) message.success(...)` 改为 `if (statsError.value) message.error(...) else message.success(...)`；新增 1 个测试文件（5 个用例）+ 1 处 `package.json` 脚本注册。

## 5. 测试结果

### RED

新增 [test-phase03b-dashboard-state-truthfulness.mjs](../../admin-h5/scripts/test-phase03b-dashboard-state-truthfulness.mjs) 在修复前运行：

```text
PASS 1. Dashboard stats request failure resolves to Error, never a fabricated zero success
PASS 2. Dashboard stats success renders the real reported values, including a genuine zero
PASS 3. A real zero-activity day is not mistaken for a request failure
PASS 4. A secondary module (marketing) failure produces its own local error state, not a global fake success
FAIL 5. Pull-to-refresh reports success only on a real success, and explicitly reports failure: a failed refresh must show an explicit failure message, mirroring OrderManage.manualRefresh -- silence is not an acceptable failure state
Phase-03B RED failures: 1
```

用例 1–4 对应第 2.1–2.5 节已经符合契约的检查点，第一次运行就是 GREEN（诚实反映"这些点本来就没有缺陷"，不是漏写断言——期间发现并修正了一处测试自身的 bug：初版用例 1 和用例 5 用 `'\n}\n'` 作为切片分隔符，而仓库里 `Dashboard.vue` 是 CRLF 换行，导致切片没有在函数结尾处截断、误把后面 `enableMarketing()` 里的 `message.error(...)` 当成了 `onPullRefresh` 的一部分，产生假 PASS；修正为读取文件后先 `.replace(/\r\n/g, '\n')` 再切片，重跑后用例 5 才正确落在 RED）。用例 5 对应第 2.6 节的真实缺口，按预期 FAIL。

### GREEN

修复第 3 节的一行代码后：

```text
$ npm run test:phase03b-dashboard-state-truthfulness
PASS 1. Dashboard stats request failure resolves to Error, never a fabricated zero success
PASS 2. Dashboard stats success renders the real reported values, including a genuine zero
PASS 3. A real zero-activity day is not mistaken for a request failure
PASS 4. A secondary module (marketing) failure produces its own local error state, not a global fake success
PASS 5. Pull-to-refresh reports success only on a real success, and explicitly reports failure
Phase-03B dashboard state truthfulness: passed
```

### 回归结果

```text
$ npm run test:dashboard-actionable-state        → ok（既有 Dashboard 契约测试，含 canSettle 会话隔离、打印机三态、营销三态、死代码清理断言，全部通过）
$ npm run test:subscription-home-and-entry       → ok（套餐状态条相关，未受影响）
$ npm run test:performance-observability         → 11/11 pass（Dashboard 的 markPageContentReady 埋点未改动，性能观测契约未受影响）
```

未运行 `npm run build`（生产构建）：本阶段改动是一行 `if/else` 逻辑重排，不涉及依赖、类型或构建配置，构建验证留给下一次触及该文件的常规改动或发布前的完整 `check` 链。

## 6. 风险评估

- **经营数据来源未被改变**：`getDashboardStats`、`getOrders`、`getMarketingPreview`、`getMerchantSystemStatus`、`getTableCouponActivity`、`getCurrentSubscription` 六个数据源的调用方式、参数和字段读取均未改动；本阶段唯一改动是刷新完成后选择哪条 `message` 提示，不影响任何数据的获取、计算或展示逻辑。
- **回归风险极低**：改动范围是一个已有 `if` 条件的取反 + 新增一个 `else` 分支，两个分支互斥（不可能同时触发或都不触发），行为在语义上是原分支的严格超集（原来的成功路径完全保留，只是新增了失败路径的反馈）。
- **未处理但已记录的观察**：第 2.4 节提到近 7 天热销榜为空时整块不渲染，这是有意为之的 OPPO 静默设计，不是缺陷，本阶段不改；如果未来产品判断新店首页需要一个"数据积累中"的引导态，应作为独立的产品决策处理，不属于状态真实性范畴。

## ACCEPTANCE：验收回答

1. **接口失败是否还会显示 0？** 不会。`statsError` 只在 `Promise.all` 成功后置假，营收/订单数等数值只在成功分支内写入；失败时 `StatCard` 走 `v-else-if="error"` 分支，不会渲染任何数字，其余次要区块整体不渲染。这在修复前后都成立——本阶段没有改变这部分逻辑，因为它本来就是对的。
2. **老板是否能区分无数据和系统失败？** 能。真实的“今天 0 营业额”会正常显示数字 0（`statsError=false`）；系统失败会显示“数据加载失败，请检查网络”加重试按钮（`statsError=true`）；两者互斥、文案不同、都不使用默认值伪装。手动刷新场景在本阶段修复后也做到了同样的区分：失败提示“刷新失败，请检查网络后重试”，成功才提示“已刷新”。
3. **Dashboard 是否围绕经营任务设计？** 是。首屏顺序已经是“待办异常 → 今日结果 → 会员/趋势/营销等辅助信息”，`todoItems` 只在真正需要处理时出现，正常状态下完全不占版面；这个顺序在代码里已经落实，不是本阶段新增的设计意图。
4. **是否修改 API 或数据库？** 否。未修改任何接口调用、请求参数、响应字段处理或数据库结构；FILES_SCOPE 内没有触碰 `saas-base`、`member-mini-client` 或任何 API 定义文件。
5. **是否符合 Phase-02 规则？** 符合。Loading/Success/Empty/Error 四态在指标、辅助模块和刷新反馈上都互斥且真实；Unknown 状态体现在打印机状态未确认时的“未确认，请点击重试”提示（沿用既有实现，未改动）；没有为了统一而改动已经正确的区块，改动范围严格限定在第 2.6 节发现的具体缺口。

```text
FINAL_DECISION=RESULT A: DASHBOARD_BUSINESS_VIEW_READY
```

本结论确认 Dashboard 的状态真实性（含本次修复的刷新反馈）已经达标并被测试锁定。信息密度、卡片数量和视觉呈现未在本阶段评估或调整——那些改动如果需要，应在证明有真实商家任务收益后，作为独立的 P2 视觉/信息层级任务处理，不属于本阶段状态真实性范畴。
