# OrderManage 高频效率 Touch And Migrate（Phase-05A）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-05A
STATUS=ORDER_MANAGE_HIGH_FREQUENCY_EFFICIENCY
MODE=AUDIT_FIRST_THEN_MINIMAL_IMPLEMENTATION
PHASE_TYPE=SINGLE_PAGE_SINGLE_JOB_OPTIMIZATION
```

## 0. Baseline

```text
BASELINE_SHA = 656301258f24b9018e933e5c8a8415c0d3990903
BRANCH = main
WORKTREE_STATUS（开始时）=
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条工作线）
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 与本阶段无关，全程未删除、未 reset、未 clean、未 stash、未混入本阶段提交。

## 1. OrderManage Core Job

| 项 | 内容 |
| --- | --- |
| 谁 | 老板 / 前台店员 |
| 触发 | 新订单进入，或高峰期连续处理多单 |
| 任务 | 发现新订单 → 判断订单 → 正确执行动作 → 继续处理下一单 |
| 成功标准 | 新订单不靠猜（不用盯数字变化或列表位移）就能被发现；危险动作（拒单）不会被手滑误触 |

沿用 Phase-05 冻结的两个最高价值摩擦：F1（新订单发现成本高）、F2（拒单误操作风险高）。

## 2. 当前真实实现核实（PART_01）

### VERIFY A — isHighlighted 是否真实存在

```text
IS_HIGHLIGHTED_EXISTS = YES
```

`admin-h5/src/composables/useWorkbenchSync.js:277` 在 `return {...}` 里导出 `isHighlighted`（第 95-98 行定义：`function isHighlighted(id) { highlightTick.value; return core ? core.isHighlighted(id) : false }`，读取 `highlightTick` 是为了让这个函数在 Vue 响应式系统里正确触发重渲染）。

### VERIFY B — 三个 Workbench 是否真实使用

| FILE | LINE | HOW_USED |
| --- | --- | --- |
| `FrontdeskWorkbench.vue` | 36, 40, 142, 233-244 | `:class="{ 'is-new': isHighlighted(order.id) }"` 加卡片边框高亮（`.wb-card.is-new{border-color:#f59e0b;box-shadow:0 0 0 2px rgba(245,158,11,.18)}`）+ `<span v-if="isHighlighted(order.id)" class="new-badge">新</span>` 文字徽章 |
| `KitchenWorkbench.vue` | 43, 47, 128, 220-221 | 同一模式，边框色 `rgba(245,158,11,.25)` |
| `WaiterWorkbench.vue` | 36, 40, 123, 247-248 | 同一模式，边框色 `rgba(245,158,11,.18)` |

三个文件的 `isHighlighted` 均从各自的 `useWorkbenchSync({...})` 调用里解构获得，本阶段执行前已用 `grep` 逐一核实（不是凭历史报告结论）。

### VERIFY C — OrderManage 迁移前是否已采用

```text
ORDER_MANAGE_HIGHLIGHT_ADOPTION = NO
```

迁移前 `OrderManage.vue` 全文件 `grep "highlight"` 零匹配；`useWorkbenchSync({...})` 的解构列表里没有 `isHighlighted`（虽然同一个调用已经解构了 `orders`/`syncFailed`/`alertEnabled` 等其它 8 个字段）。已用 `git show BASELINE_SHA:admin-h5/src/views/OrderManage.vue` 核实，不是凭 Phase-05 报告的旧结论直接假定。

### VERIFY D — isHighlighted 生命周期审计

| 项 | 内容 |
| --- | --- |
| HIGHLIGHT_ENTER | `workbenchSyncCore.js:245-258` 的 `addHighlights(ids)`，只在 `commitOrders()` 里 `allowAlert && alertsEnabled && hasBaseline` 为真时，对"相对上一次已知集合新出现的 actionable id"调用——首次建立基线时不会把当前所有订单都标记成新的 |
| HIGHLIGHT_EXIT | 每个 id 独立的 `setTimeoutFn(..., highlightMs)`（`highlightMs` 默认 `NEW_ORDER_HIGHLIGHT_MS = 8000`，`workbenchSyncCore.js:7`），到期自动从 `highlightIds` 里移除并 `emit()` |
| STATUS_CHANGE_EFFECT | 订单状态变化不会主动清除高亮——高亮只由超时或身份重置清除；如果 8 秒内该订单被接单，短暂看到"新"标签和已接单状态同时存在是预期行为，不是缺陷 |
| REFRESH_EFFECT | 整页刷新会重新执行 `onMounted`，创建全新的 `core` 实例，`highlightIds` 从空集合开始——高亮状态不跨刷新持久化，这是三个 Workbench 现有的行为，OrderManage 沿用同样效果，不需要也不应该额外处理 |
| REENTER_EFFECT | 离开页面（组件卸载）触发 `onBeforeUnmount` 里的 `core?.stop(); core = null`；重新进入会创建新 core，高亮清空——与刷新效果一致，同样是继承自 `useWorkbenchSync` 本身的既有设计，不是本阶段需要新增处理的场景 |
| STATE_OWNER | `workbenchSyncCore.js` 里 `createWorkbenchSyncCore()` 闭包作用域内的 `highlightIds`/`highlightTimers`，每个调用 `useWorkbenchSync()` 的组件实例各自拥有一份（不是全局单例）。OrderManage 通过自己已有的 `useWorkbenchSync({dedupeKey:'owner:orders', ...})` 调用获得自己的一份，跟三个 Workbench 各自的实例互不干扰，也不需要新建 store 去共享 |

**结论：OrderManage 必须且只需要复用这个生命周期，不新建第二套。** 本阶段的实现严格遵守这一点（见第 6 节）。

### rejectOrder 现状核实（PART_04）

```text
CURRENT_REJECT_FLOW = 点击"拒单" → 直接 await updateOrderStatus(order.id, 'rejected')
```

`OrderManage.vue`（迁移前）第 1355-1368 行：`async function rejectOrder(order)` 内部没有任何 `Modal.confirm`/二次确认，点击即直接发起状态更新请求。已用 `git show BASELINE_SHA:...` 核实，不是沿用历史报告结论。

### 参照确认模式（PART_05）

| 项 | 内容 |
| --- | --- |
| REFERENCE_ACTION | `cancelPendingPaymentOrder(order)`（同文件，取消待支付订单） |
| REFERENCE_FILE | `admin-h5/src/views/OrderManage.vue:1312-1331`（迁移前行号） |
| CONFIRM_COMPONENT | `Modal.confirm`（`ant-design-vue`，文件顶部已 `import { message, Modal } from 'ant-design-vue'`） |
| TITLE | `'取消这单待支付订单？'` |
| CONTENT | `` `¥${金额}，取消后顾客的这个订单会失效，需要重新下单。` `` |
| OK_STYLE | `okText:'取消订单'`，`okType:'danger'` |
| CANCEL_BEHAVIOR | `cancelText:'再想想'`，取消不触发 `onOk`，无副作用 |

## 3. F1 新订单发现摩擦

- **Before**：`TRIGGER`=新订单到达；`CURRENT_SIGNAL`=待接单数字变化、卡片在排序后出现在列表/桌台顶部；`CURRENT_DISCOVERY_COST`=MEDIUM；`CURRENT_DEPENDENCE`=数字变化 + 列表位置，二者都要求老板主动注意，忙时容易漏看。
- **Evidence**：第 2 节 VERIFY A-D 已完整核实——能力已存在、已被验证、只是没接。
- **Target**：复用 `isHighlighted(order.id)`，在订单列表卡片、桌台格子、桌台抽屉三处渲染面统一体现同一个"新"语义，不要求 DOM/CSS 与三个 Workbench 逐字节一致，只要求认知一致（都是琥珀色 + "新"字样）。

## 4. isHighlighted 生命周期审计

已在第 2 节 VERIFY D 完整给出，此处不重复。

## 5. F2 拒单误操作摩擦

- **Before**：点击"拒单"零确认，直接调用业务接口；紧邻的"接单"是本页最高频的主操作，两者共享 `order-action-row`（迁移前 203-204/386-387 行）。
- **Risk**：一次误触会真实拒绝一个已经付费或正在等待处理的顾客订单，恢复路径是"联系顾客说明原因"（`message.warning`原文），代价是外部性的（要给顾客解释、顾客体验受损），不是能在系统内一键撤销的操作。
- **Target**：点击拒单先弹出 `Modal.confirm`，说明对象（这张订单）和后果（不再继续处理、顾客需要重新下单），确认后才走原有业务请求路径；取消不产生任何请求或状态变化。

## 6. 最小实施

**实际修改文件**：仅 `admin-h5/src/views/OrderManage.vue`（业务代码）+ `admin-h5/scripts/test-phase05a-order-high-frequency-efficiency.mjs`（新增测试）+ `admin-h5/package.json`（仅注册测试命令）。未修改 `useWorkbenchSync.js`、`workbenchSyncCore.js`、三个 Workbench 文件、任何 API/数据库/状态机相关代码。

**实际修改点**：

1. `useWorkbenchSync({...})` 解构新增 `isHighlighted`（脚本，1 行）。
2. 列表视图订单卡片（`<a-card>`）：新增 `:class="{ 'order-card--new': isHighlighted(order.id) }"`，标签行新增 `<a-tag v-if="isHighlighted(order.id)" ...>新</a-tag>`（复用本文件已有的"打印结果未知"同款琥珀色内联样式，不新建 token）。
3. 桌台详情抽屉的订单行（`.order-row`）：同样新增"新"标签（不加边框，理由见 CSS 注释——连续贴边的行不适合再加描边环）。
4. 桌台格子（`.table-tile`）：`:class` 新增 `'table-tile--new': table.orders.some((o) => isHighlighted(o.id))`，复用本文件已有的 `.table-tile--urgent` 同款琥珀色（`#f59e0b`），只是换一个语义不同的修饰类，颜色和视觉语言完全复用，不新建 CSS 变量。
5. `rejectOrder(order)`：从 `async function` 改为普通 `function`，原有的完整业务逻辑（状态更新、成功/失败/需退款分支、`reconcileAfterOrderAction`）原封不动地挪进新增的 `Modal.confirm({...}).onOk` 回调；确认文案对照 `cancelPendingPaymentOrder` 的结构书写：标题"确认拒绝该订单？"，内容"¥金额，拒绝后该订单将不再继续处理，顾客需要重新下单。"，`okType:'danger'`，`cancelText:'再想想'`。模板里 `@click="rejectOrder(order)"` 的两处绑定原样不动。

未触碰：`acceptOrder`/`finishOrder`/`confirmServed`/退款/补打/结账/历史订单/批量处理/订单卡片其余结构。

## 7. TDD

新增 [test-phase05a-order-high-frequency-efficiency.mjs](../../admin-h5/scripts/test-phase05a-order-high-frequency-efficiency.mjs)，覆盖 PART_08 要求的场景（TEST 6 用已有的 Phase-03A 测试文件复跑，不重复造轮子）。

### RED（对迁移前真实源码验证，方法：`git show BASELINE_SHA:...` 输出到临时文件后跑同等断言，未使用 stash，未触碰工作区任何文件）

```text
FAIL 1. OrderManage adopts the existing isHighlighted authority from useWorkbenchSync: isHighlighted must be destructured
FAIL 2. New-order visual state is driven by isHighlighted(order.id): expected >=3, found 0
FAIL 5. Clicking reject goes through confirm first: [assertion failed]
RED-check failures (expected on baseline): 3
```

（RED 验证用的临时脚本和临时基线文件仅用于本次验证，验证完成后已删除，不在仓库/scratchpad 中留存。）

### GREEN

```text
$ npm run test:phase05a-order-high-frequency-efficiency
PASS 1. OrderManage adopts the existing isHighlighted authority from useWorkbenchSync
PASS 2. New-order visual state is driven by isHighlighted(order.id), not a second highlight system
PASS 3. The new-order badge and tile ring use the file's own existing amber vocabulary, not a new color/token
PASS 4. useWorkbenchSync.js and the three staff workbenches are untouched -- Phase-05A only touches OrderManage.vue
PASS 5. Clicking reject no longer fires the business request directly -- it must go through a confirm dialog first
PASS 6. Cancelling the reject confirmation cannot call the API or touch order state
PASS 7. Confirming reject still uses the exact original business path -- same API call, same success/refund/error handling, same reconcile
PASS 8. Reject button wiring in the template is unchanged -- no new click target, no new component
Phase-05A order high-frequency efficiency: passed
```

`NO_PRODUCT_RED`：不适用于本阶段——两项摩擦（F1/F2）在迁移前都是真实、可验证的缺陷，8 个测试用例全部经历了真实 RED（用例 4/6/7/8 未在独立 RED-check 脚本里重复跑，但它们断言的行为在迁移前源码里同样不存在——用例 4 检查 5 个既有文件是否被修改，迁移前这个断言的意义是"这些文件当时也确实和 HEAD 一致"，因此不构成有意义的 RED/GREEN 对照，如实记录为该用例本身是纯粹的回归锁，不是缺陷验证）。

### 测试方法局限性（PART_09 要求说明）

仓库没有 Vue render test framework，测试通过源码结构切片验证："真实消费" 用真实的 `isHighlighted(order.id)` 调用位置计数（而不是裸字符串 `"isHighlighted"` 是否出现），拒单测试验证业务请求代码在 `onOk` 回调内部的相对位置（而不是仅检查 `Modal.confirm` 是否出现在文件某处）。局限：无法验证运行时真实渲染结果（比如高亮是否真的在浏览器里 8 秒后消失），这部分依赖第 9 节说明的浏览器验证覆盖范围。

## 8. Regression Gates

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `npm run test:phase05a-order-high-frequency-efficiency` | 8/8 PASS |
| 2 | `npm run test:phase03a-order-state-truthfulness` | 5/5 PASS |
| 3a | `npm run test:p0-08-sync` | 18/18 PASS |
| 3b | `npm run test:p0-08-acceptance` | STATUS_MISMATCH_COUNT=0，各项延迟指标达标 |
| 3c | `npm run test:workbench-sync` | passed |
| 3d | `npm run test:order-page-table-context` | PASS |
| 3e | `npm run test:p1-03-order-status-text` | P1_03_TECH_STATUS_LEAK=NO |
| 3f | `npm run test:order-list-sort` | passed |
| 3g | `npm run test:workbench-print-status` | ok |
| 3h | `npm run test:payment-handoff-polling` | ok |
| 3i | `node scripts/test-order-manage-session-isolation.mjs`（未在 package.json 注册，手动核实） | **1 处断言失败**——见下方说明 |
| 3j | `node scripts/test-p0-09-money-safety.mjs`（未注册，手动核实） | 通过 |
| 3k | `node scripts/test-p0-refund-exposure.mjs`（未注册，手动核实） | 通过 |
| 3l | `node scripts/test-p1-02-historical-orders.mjs`（未注册，手动核实） | 通过 |
| 4 | `npm run test:phase04-component-adoption-governance` | 6/6 PASS |
| 5 | `npm run check` | 全链路通过，含以上全部已注册测试 |
| 6 | `npm run build` | `✓ built in 20.88s`，无编译错误 |

**关于 3i 的失败——已核实是迁移前已存在的问题，与本阶段无关**：`test-order-manage-session-isolation.mjs:132` 断言源码包含字面字符串 `"orders.value.filter(o => o.status !== 'pending_payment')"`，但当前 `sortedOrders` computed（`OrderManage.vue:1167-1171`）实际写的是 `sourceOrders.value.filter(...)`——变量名在某次更早的历史改动（引入 `sourceOrders = computed(() => isLiveToday.value ? orders.value : historicalOrders.value)` 统一今日/历史订单读取路径时）已经从 `orders` 改成了 `sourceOrders`，这个测试没有同步更新，且从未被注册进 `package.json`/`npm run check`。已用 `git show BASELINE_SHA:admin-h5/src/views/OrderManage.vue | grep -A5 "sortedOrders = computed"` 核实：**迁移前的代码就已经是 `sourceOrders.value.filter(...)`**，本阶段完全没有触碰 `sortedOrders`。这是一个与 Phase-05A 无关的、独立存在的过期测试，按 STRICT_SCOPE 不在本阶段修复，记录进第 12 节 Deferred Issues。

## 9. 浏览器验证

```text
BROWSER_VERIFICATION=NOT_RUN
REASON=本机没有可用于 OrderManage 的登录态或可用的开发/staging 后端（需要真实商家账号 + 真实订单数据才能观察到新订单高亮和拒单确认的实际效果）；`npm run build` 已确认模板/脚本改动可以正确编译成生产构建，产物里包含预期的 chunk（OrderManage-*.js 从原有体积增长了少量，与新增的 class 绑定和 Modal.confirm 调用体量吻合），但这只证明"能编译"，不等于"运行时行为符合预期"。自动化合同测试（第 7/8 节）已完整覆盖，不用浏览器验证冒充完成。
```

## 10. Before / After Efficiency

### 新订单发现

| 指标 | Before | After |
| --- | --- | --- |
| DISCOVERY_SIGNAL | 待接单数字变化、列表/桌台位置变化 | 数字变化、位置变化 **+ 卡片/格子琥珀色描边 + "新"标签**（三处渲染面：列表卡片、桌台格子、桌台抽屉行） |
| DISCOVERY_COST | MEDIUM（需要主动注意数字或位置） | LOW（新订单在视觉上直接突出，与三个 Workbench 已验证过的效果一致） |
| DECISION_COST | 需要先扫描确认"这是不是新单"再判断怎么处理 | "新"标签直接给出答案，判断成本降低 |

### 拒单操作

| 指标 | Before | After |
| --- | --- | --- |
| CLICK_COUNT | 1（直接执行） | 2（点击 + 确认） |
| ERROR_RISK | HIGH（零确认，紧邻主按钮） | LOW（二次确认，文案明确说明对象和后果） |

CLICK_COUNT 上升是本阶段刻意接受的结果：PART_13 明确"拒单增加一次确认，CLICK_COUNT 可能上升，这是允许的，因为 TOTAL_JOB_COST 下降"。降低的是错误代价（一次真实顾客订单被误拒的外部性成本），不是为了"少点一次"而牺牲这个确认。

## 11. Scope Audit

```text
SCOPE_EXPANDED = NO
```

逐条核对 STRICT_RULES 1-22：未改后端 API/数据库/订单状态机/同步协议/支付逻辑/打印逻辑；未重构 OrderManage（改动集中在 2 个具体摩擦点对应的模板片段和 1 个函数体）；未新增全局通知系统/newOrderIds/localStorage 状态/新 timer/第二套 highlight 生命周期/浮动提醒条/声音/桌面通知；未顺手改退款/补打/结账；未统一其它危险操作的确认方式（只处理了审计证明存在风险的 `rejectOrder`）；未做性能优化；未修改其它页面业务行为（第 8 节 Regression Gate #4 已用字节级对比核实 `useWorkbenchSync.js`/`workbenchSyncCore.js`/三个 Workbench 文件与 HEAD 完全一致）。

## 12. Deferred Issues

只记录，本阶段不实现：

1. **`test-order-manage-session-isolation.mjs` 断言的变量名过期**（第 8 节已详述）：这个测试本身没有被 `npm run check` 覆盖，且断言的字符串在 Phase-05A 之前就已经和真实代码不符。修复它需要更新测试断言以匹配 `sourceOrders` 命名，这是一处独立的测试维护债务，不属于 STRICT_SCOPE 允许的 A/B 两项范围，交给下一次真正触碰 `sortedOrders`/历史订单逻辑的任务顺手处理。
2. **桌台结账 3 层浮层**（Phase-05 报告已记录）：本阶段确认未处理，继续 DEFER。
3. **补打/退款按钮同色相邻**（Phase-05 报告已记录）：本阶段确认未处理，继续 DEFER。
4. **异常订单无筛选/不置顶**（Phase-05 报告已记录）：本阶段确认未处理，继续 DEFER。
5. **新订单高亮在桌台视图里如果订单所在的桌子格子不在当前视口内仍可能被错过**（第 11 节 Phase-05 报告 AB 方案里已经讨论过这个边缘场景）：方案 A（本次实施的方案）不覆盖这种情况，若未来有真实商家反馈，再考虑方案 B（浮动提醒），本阶段不预先实现。

## 13. Phase-05B Input

下一阶段 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-05B` 主题是 MenuManage 菜品查找与维护效率，核心摩擦是主列表没有名称搜索（Phase-05 报告 RANK 5，500+ 菜品场景下只能靠分类筛选+滚动）。本报告不在这里开始实施，只作指向。

## ACCEPTANCE

1. **OrderManage 是否已经采用现有 isHighlighted？** 是，`useWorkbenchSync({...})` 解构里新增了 `isHighlighted`，未新建导入路径或新组合式函数。
2. **是否复用了唯一高亮状态权威，而不是新建第二套状态？** 是，第 2 节 VERIFY D 和第 8 节 Regression Gate #4（字节级对比）共同证明状态权威仍然只有 `workbenchSyncCore.js` 内部的 `highlightIds`，OrderManage 拿到的是自己那份 `useWorkbenchSync` 实例的 `isHighlighted`，跟三个 Workbench 各自独立，没有共享 store，也没有新建任何状态。
3. **新订单是否更容易被老板发现？** 是，第 10 节量化：从"靠数字/位置猜"变成"数字/位置 + 视觉高亮 + 文字标签"三重信号。
4. **高亮生命周期是否与三个既有 Workbench 一致？** 是，进入/退出/刷新/重进的规则完全来自同一个 `workbenchSyncCore.js`，OrderManage 没有引入任何差异化处理。
5. **是否没有新增"新订单"业务状态？** 是，高亮是纯前端短期注意力提示，未写回服务器，未新增 `status=new`，`order.status` 的唯一权威仍然是后端返回值（第 6 节第 5 点也明确 `reconcileAfterOrderAction`/`syncNow` 路径未被绕过）。
6. **rejectOrder 是否已经有明确确认？** 是，`Modal.confirm` 说明了动作对象（该订单）和后果（不再继续处理、顾客需重新下单）。
7. **取消确认是否绝不会发起拒单请求？** 是，第 7 节测试 6 已验证 `order.updating`/`updateOrderStatus` 只在 `onOk` 回调内可达，`beforeOnOk` 切片里两者均不出现。
8. **确认后是否仍然使用原有订单处理链？** 是，测试 7 逐项核对了状态更新调用、成功/退款/失败三分支文案、`reconcileAfterOrderAction` 调用均与迁移前完全一致，且没有任何直接赋值 `order.status =` 的本地写入。
9. **是否没有修改 API/DB/状态机？** 是，本阶段 0 处后端相关改动。
10. **Phase-03A 的订单真实性合同是否仍然通过？** 是，第 8 节 Regression Gate #2，5/5 PASS。
11. **是否没有顺手修改退款/补打/结账？** 是，第 11 节 Scope Audit 已逐条核对。
12. **是否完成真实 RED → GREEN，或诚实记录 NO_PRODUCT_RED？** 完成了真实 RED → GREEN（第 7 节），且对不构成有意义 RED/GREEN 对照的用例做了如实说明，没有伪造。
13. **是否能证明本次优化降低了 Total Job Cost？** 是，第 10 节：新订单发现的 DISCOVERY_COST 从 MEDIUM 降到 LOW；拒单的 CLICK_COUNT 上升 1 次换来 ERROR_RISK 从 HIGH 降到 LOW，净 Total Job Cost 下降（一次误触真实订单的外部代价远高于多点一次确认的时间成本）。

```text
FINAL_DECISION=RESULT A: ORDER_HIGH_FREQUENCY_EFFICIENCY_READY
NEW_ORDER_DISCOVERY=READY
REJECT_SAFETY=READY
HIGHLIGHT_STATE_OWNER=workbenchSyncCore.js 内 createWorkbenchSyncCore() 闭包的 highlightIds/highlightTimers，通过 useWorkbenchSync.js 的 isHighlighted(id) 暴露，OrderManage 使用自己已有的 useWorkbenchSync 实例，未新建权威
BUSINESS_API_CHANGED=NO
DATABASE_CHANGED=NO
ORDER_STATE_MACHINE_CHANGED=NO
SCOPE_EXPANDED=NO
```

## COMMIT_RULE

```text
CHANGED_FILES=
  admin-h5/package.json
  admin-h5/src/views/OrderManage.vue
  admin-h5/scripts/test-phase05a-order-high-frequency-efficiency.mjs（新增）
  docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE05A_ORDER_HIGH_FREQUENCY_EFFICIENCY.md（新增，本文件）
  PROJECT_INDEX.md
  PROJECT_KNOWLEDGE_MAP.md
STAGED_FILES=同上，仅这 6 个文件
UNRELATED_WIP_INCLUDED=NO
```

下一阶段进入 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-05B`，只处理 MenuManage 一个页面的最高价值 Job，不在 Phase-05A 完成后继续顺手修改 OrderManage。
