# OrderManage 状态真实性 Touch And Migrate（Phase-03A）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03A
STATUS=ORDER_MANAGE_STATE_TRUTHFULNESS_MIGRATION
PREVIOUS_PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-02
REFERENCE=ADMIN_FRONTEND_CONSTITUTION.md V1.0, ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md, ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md
REPOSITORY_BASELINE_SHA=25d874645e0d2f0d4c50e6e6c9e3c6b6c8f5e3f0
SCOPE=admin-h5/src/views/OrderManage.vue（状态展示逻辑）
BUSINESS_CODE_CHANGE=NO
API_CHANGE=NO
ORDER_STATE_MACHINE_CHANGE=NO
NEW_FEATURE=NO
FULL_PAGE_REWRITE=NO
```

## 1. 当前问题

本阶段按 [ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md §4](./ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md) 列出的五个检查点逐条审计了 `OrderManage.vue` 当前源码（而不是只看历史审计结论），结果是：**五个检查点全部已经符合契约，本阶段没有发现需要修复的状态失真问题。**

| 检查点 | 要求 | 当前源码证据 | 结论 |
| --- | --- | --- | --- |
| 1. 首次加载失败 | 接口失败 MUST NOT 显示为空订单 | `fetchOwnerFull()` 在 `body?.code !== 200 \|\| !Array.isArray(body.data)` 时 `throw`（[OrderManage.vue:953](../../admin-h5/src/views/OrderManage.vue)），核心同步器捕获后置 `syncFailed = true` 且不清空 `orders`；`orderLoadError = computed(() => syncFailed.value && orders.value.length === 0)`（[:1001](../../admin-h5/src/views/OrderManage.vue)）；模板 `v-if="orderLoadError"` 渲染独立错误态，且求值顺序在空态 `v-else-if` 之前（[:80](../../admin-h5/src/views/OrderManage.vue) 早于 [:95](../../admin-h5/src/views/OrderManage.vue)） | 已符合 |
| 2. 历史订单加载失败 | 分页/刷新失败 MUST NOT 覆盖已有数据为空 | `loadHistoricalOrders()` 只在 `try` 成功路径写入 `historicalOrders.value`；失败分支（`res.code !== 200` 或 `catch`）只置 `historicalError.value = true` 并 `return`，不清空 `historicalOrders`（[:1119-1131](../../admin-h5/src/views/OrderManage.vue)）；模板对历史 Tab 同样先判 `historicalError` 再判空（[:320](../../admin-h5/src/views/OrderManage.vue) 早于 [:333](../../admin-h5/src/views/OrderManage.vue)） | 已符合 |
| 3. 空状态区分 | Empty 仅在请求成功且确认为 0 条时出现 | 空态条件为 `!loading && !syncFailed && orders.length === 0`（[:95](../../admin-h5/src/views/OrderManage.vue)），三个条件缺一都不进入空态；`syncFailed` 由核心同步器仅在请求失败时置真 | 已符合 |
| 4. 刷新反馈 | 只有确认同步成功才能提示“刷新成功”；失败必须显示失败原因 | `manualRefresh()` 先 `await loadOrders()` 拿到 `result`，`result?.ok !== true` 时 `message.error('刷新失败，请检查网络后重试')` 并 `return`，成功提示 `message.success('已刷新', 1)` 在其之后（[:1031-1039](../../admin-h5/src/views/OrderManage.vue)）；且失败时还有常驻的 `v-if="syncFailed && orders.length > 0"` 警示条（[:71-77](../../admin-h5/src/views/OrderManage.vue)），不是只靠一闪而过的 toast | 已符合 |
| 5. 状态来自真实后端 | 禁止前端自行推导业务状态 | 订单动作（接单/出餐/结账/退款/补打等）在成功或失败后统一 `await reconcileAfterOrderAction()`（[:1297](../../admin-h5/src/views/OrderManage.vue) 起，见 [:1323-1522](../../admin-h5/src/views/OrderManage.vue) 各处），未发现直接用接口响应体覆写 `order.status` 的写法 | 已符合 |

**补充发现（不在原五点内，但属于同一状态真实性范畴）**：Phase-02 规则新增的 `unknown` 状态在打印结果上已经有具体实现——`order.printStatus === 'unknown'` 渲染“打印结果未知”标签，颜色为琥珀色 `#b45309/#fffbeb/#fde68a`（[:174](../../admin-h5/src/views/OrderManage.vue)），与“打印失败”的红色 `#dc2626/#fef2f2/#fecaca`（[:173](../../admin-h5/src/views/OrderManage.vue)）和成功态使用的绿色均不同，未借用成功或失败色假定结果。

## 2. Jobs 分析

沿用 [ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md §2.2](./ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md) 已定义的 OrderManage Jobs：

- **用户**：前台 / 店长。
- **任务**：订单进入和流转时，快速接单、出餐、结账、处理打印或支付异常。
- **成功标准**：新订单不遗漏，状态不含糊，操作结果可确认。
- **核心动作**：接单、出餐、结账、补打、退款。
- **禁止展示**：把营销、套餐说明或经营统计堆在接单主路径前面。

状态真实性是这个 Job 的前提条件，不是附加要求：如果“订单同步失败”被显示成“今天没有订单”，店员会漏单；如果“刷新失败”被显示成“已刷新”，店长会误信数据是最新的从而漏看新订单。第 1 节的审计结果显示，当前实现已经把这两个最高风险的失真场景堵住了。

## 3. 修改方案

**结论：本阶段不需要修改 `OrderManage.vue` 的任何业务代码。**

原计划是按 Constitution/Phase-02 的状态合同做最小 Touch And Migrate；但按 [AI_ENTRYPOINT.md](../../AI_ENTRYPOINT.md) 的要求先审计现状、不假设历史结论有效之后发现，第 1 节列出的五个检查点已经在当前代码中实现，并且已有 `scripts/test-p0-08-sync.mjs` 中的以下用例在持续保护它们：

- `Order page distinguishes sync error from an empty successful result`
- `Owner order adapters reject fulfilled business errors instead of normalizing them to empty`
- `Manual order refresh only reports success for an acknowledged successful sync`
- `Historical order request failure has an error state and cannot fall through to empty`

在这种情况下继续“修改”页面代码，唯一可能的后果是引入无收益的变更或误伤已经正确的逻辑，这违反 Constitution §7/§8 的 Touch And Migrate 原则（迁移必须以商家任务改善或风险降低为目的，MUST NOT 为了流程完整而变更代码）和本阶段 STRICT_RULES 的“最小修改”。

因此，本阶段的实际产出收窄为：

1. 用真实源码逐条核实第 1 节五个检查点（而不是复述 Phase-01 的历史结论）；
2. 新增一份专门锁定这五个场景 + Unknown 场景的回归测试 [scripts/test-phase03a-order-state-truthfulness.mjs](../../admin-h5/scripts/test-phase03a-order-state-truthfulness.mjs)，并接入 `package.json` 的 `test:phase03a-order-state-truthfulness` 与 `check` 链，防止未来改动在没有测试提醒的情况下悄悄回退这些行为；
3. 产出本报告作为 Phase-03A 的验收证据。

这仍然符合 FILES_SCOPE：只新增了“相关测试文件”，未触碰 `saas-base`、`member-mini-client` 或任何 API。

## 4. 状态合同变化

| 状态 | Before | After |
| --- | --- | --- |
| Error（首次同步失败） | 已符合：`orderLoadError` 独立渲染 error alert，早于 empty 分支 | 无变化；新增测试锁定该行为 |
| Empty（成功且 0 条） | 已符合：`!loading && !syncFailed && orders.length === 0` | 无变化；新增测试显式覆盖“成功返回 0 条”这一具体场景（此前只有隐式覆盖） |
| 刷新失败保留旧数据 | 已符合：失败分支不调用 `commitOrders`，`orders` 不被清空；同时有常驻警示条 + toast | 无变化；新增测试用真实同步核心重放“先成功后失败”的场景，直接断言 `orders` 数组内容不变 |
| Success | 已符合 | 无变化 |
| Unknown（打印结果） | 已符合：独立琥珀色标签，不复用成功/失败色 | 无变化；新增测试断言标签存在且颜色与成功/失败色不重叠，防止未来被“视觉统一”成红色或绿色 |

**净变化**：0 处业务逻辑改动；新增 1 个测试文件（5 个用例）+ 1 处 `package.json` 脚本注册。

## 5. 测试结果

### RED

未产生传统意义的 RED。审计确认当前实现已满足全部五个契约点，因此新增的 [test-phase03a-order-state-truthfulness.mjs](../../admin-h5/scripts/test-phase03a-order-state-truthfulness.mjs) 从第一次运行起就是 GREEN，没有可修复的缺陷驱动“先写会失败的测试”这一步。这是一个诚实的审计结论，不是省略了 TDD 流程：五个用例分别对应 TDD_REQUIREMENT 里列出的五个场景，均通过对真实 `workbenchSyncCore` 的行为重放（而不是 mock 断言字符串）来验证，第 3 个用例额外核对了 `manualRefresh` 源码中失败判断先于成功提示的顺序。

### GREEN

```text
$ npm run test:phase03a-order-state-truthfulness
PASS 1. First order sync failure resolves to Error, not Empty
PASS 2. Order sync succeeding with zero orders resolves to Empty
PASS 3. A refresh failure after a prior success preserves existing orders and reports failure
PASS 4. Order sync succeeding with data resolves to Success
PASS 5. Unrecoverable-but-not-confirmed-failed print result renders as Unknown, not Success or Error
Phase-03A order state truthfulness: passed
```

同时复跑了受影响面相邻的既有测试，确认未引入回归：

```text
$ npm run test:p0-08-sync        → 18/18 PASS
$ npm run test:p0-08-acceptance  → 数据一致性/延迟指标全部达标（STATUS_MISMATCH_COUNT=0）
$ npm run test:workbench-sync    → passed
$ npm run test:workbench-print-status → ok
$ npm run test:order-page-table-context → PASS
$ npm run test:p1-03-order-status-text → P1_03_TECH_STATUS_LEAK=NO
```

## 6. 风险评估

- **订单业务未被改变**：本阶段未修改任何 `.vue` 业务逻辑，只新增测试文件和一行 `package.json` 脚本注册；订单状态机、接口字段、权限、支付/退款流程均未触碰，符合 STRICT_RULES 第 1–10 条。
- **回归风险极低**：新增测试是纯增量文件，不影响现有测试执行；`package.json` 的 `check` 链新增一步，属于追加而非修改已有命令。
- **遗留风险（本阶段之外，仅记录不处理）**：`manualRefresh` 失败时的 `message.error` 文案是“刷新失败，请检查网络后重试”，与常驻警示条“订单同步失败，当前显示的是上次数据”并存，两者语义一致但文案不完全统一；这是 P2 级视觉/文案一致性问题，不是状态真实性问题，按 Constitution 路线图应留到 P2 阶段处理，本阶段不顺手改。

## ACCEPTANCE：验收回答

1. **接口失败是否还会显示空订单？** 不会。`orderLoadError` 在 `syncFailed && orders.length === 0` 时为真，渲染独立的 error alert，且模板求值顺序在空态分支之前；已有行为测试和新增测试 1 共同覆盖。
2. **空状态是否只代表真实空数据？** 是。空态条件要求 `!loading && !syncFailed && orders.length === 0` 三者同时成立，任一失败分支都无法落入空态；新增测试 2 显式覆盖“成功返回 0 条”这一具体场景。
3. **刷新失败是否保留当前订单？** 是。失败路径不调用写入订单数组的 `commitOrders`，`orders` 保持刷新前的内容，并同时有常驻警示条和失败 toast；新增测试 3 用真实同步核心重放验证。
4. **是否修改后端合同？** 否。未修改任何 API、数据库、订单状态机或接口字段，`FILES_SCOPE` 内没有触碰 `saas-base`、`member-mini-client` 或 API 定义文件。
5. **是否符合 Phase-02 状态规则？** 符合。Loading/Success/Empty/Error 四态互斥且定义清晰；新增确认了 Phase-02 引入的 Unknown 状态已经在打印结果维度有具体、独立于成功/失败色的实现，不存在用默认值或颜色掩盖未知状态的情况。

```text
FINAL_DECISION=RESULT A: ORDER_STATE_TRUTHFULNESS_READY
```

本结论确认 OrderManage 的状态真实性已经达标并被测试锁定。不代表 OrderManage 的其它维度（页面复杂度、信息优先级、超大文件风险）已经处理完——那些属于 [ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md §7](./ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md) P0 路线的其它条目，需要独立的后续任务。
