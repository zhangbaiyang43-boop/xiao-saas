# 高频任务效率基线（Phase-05）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-05
STATUS=HIGH_FREQUENCY_TASK_EFFICIENCY
MODE=AUDIT_FIRST_AND_PRIORITIZE
PHASE_TYPE=CROSS_PAGE_EFFICIENCY_BASELINE
```

## 0. Baseline

```text
BASELINE_SHA = c8547876929bf9538d0e6e502f62739019ef7c77
BRANCH = main
WORKTREE_STATUS（开始时）=
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条工作线）
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 与 admin-h5 页面效率无关，本阶段全程未清理、未 reset、未提交。本阶段按 IMPLEMENTATION_BOUNDARY 不修改任何业务代码，只审计、量化、排序，写入范围仅限 `docs/frontend/`、`PROJECT_INDEX.md`、`PROJECT_KNOWLEDGE_MAP.md`。

## 1. Phase-05 目标

Phase-03 确认了后台"说真话"（状态真实），Phase-04 确认了后台"用一致的方法说话"（表达一致）。Phase-05 回答的是完全不同维度的问题：**老板/店员真正干活时，能不能用更少的时间、更少的判断、更低的错误风险完成任务。** 评价标准不是页面数量、组件数量或视觉统一度，而是六项成本：发现成本（DISCOVERY_COST）、判断成本（DECISION_COST）、操作成本（ACTION_COST）、出错代价（ERROR_COST）、恢复成本（RECOVERY_COST）、重复成本（REPETITION_COST）。

本阶段严格排除已在 Phase-03/04 处理过的问题（状态真实性、组件采用、UI 框架边界、性能监控），除非某个效率问题的根因直接是这些因素造成的。

## 2. 用户角色与核心 Jobs

| 角色 | 核心 Jobs |
| --- | --- |
| 老板 | 巡店/看结果、处理异常、维护菜单价格与上下架、必要时查会员 |
| 店员/收银 | 接单出餐、打印/补打、代客下单、结账、核销优惠券、前台查会员办理业务 |
| 运营人员 | 维护菜品信息、管理会员分层与发券 |

Dashboard 承担"发现问题、进入任务"；OrderManage/MenuManage/CustomerList 承担"真实操作"——本阶段重点审计后三者，Dashboard 只审计交接质量（第 6 节）。

## 3. OrderManage 任务链（真实源码审计，非历史印象）

按 ORDER_TASKS 十项逐一核对当前 `OrderManage.vue`（1973 行）及其依赖的 `useWorkbenchSync.js`/`workbenchSyncCore.js`：

| TASK | ENTRY | CURRENT_STEPS | CURRENT_CLICKS | ERROR_RISK | FRICTION |
| --- | --- | --- | --- | --- | --- |
| 1. 新订单发现 | 列表/桌台自动重排到顶部 | 0 步（自动置顶） | 0 | LOW | **`useWorkbenchSync.js` 导出的 `isHighlighted(id)` 从未被 `OrderManage.vue` 消费**——新订单只靠"待接单"数字变化和列表位置移动被发现，没有任何视觉高亮或"新"标签。三个员工工作台（`FrontdeskWorkbench.vue:36,40`、`KitchenWorkbench.vue:43,47`、`WaiterWorkbench.vue:36,40`）都已经用 `isHighlighted(order.id)` 加了 `.is-new` 边框高亮 + "新"徽章（`FrontdeskWorkbench.vue:233-244`），**唯独老板/前台主用的 OrderManage.vue 没有**（全文件 grep "highlight" 零匹配） |
| 2. 查看订单关键信息 | 列表卡片/桌台抽屉 | 0 步（一次性展示） | 0 | LOW | 列表视图信息一次性展示；桌台视图需先开抽屉（`openTableDetail`）才能看到同等详情，比列表深一层 |
| 3. 接单 | "接单"按钮 | 1 步 | 1 | LOW | 无确认，符合高频动作应该短的原则 |
| 4. 完成订单 | "出餐完成"+"确认已上菜" | 2 步（两个独立动作） | 2 | LOW | 出餐和上菜是拆开的两个真实业务状态，不是可合并的重复步骤 |
| 5. 拒单/取消 | "拒单"按钮 | 1 步，**零确认** | 1 | **HIGH** | `rejectOrder`（1352-1365）直接执行，无 `Modal.confirm`；紧邻主操作"接单"（同一 `order-action-row`，203-204/386-387）。对照同文件 `cancelPendingPaymentOrder`（1309-1328）*有*二次确认——同一文件内两个语义相近的取消类动作，确认标准不一致 |
| 6. 打印/补打 | "补打小票"（`printStatus` 为 failed/unknown 时出现） | 1 步 | 1 | LOW | 无确认，符合预期；但视觉上和"拒单"用同一个 `order-action-btn--reject` 危险色 |
| 7. 异常订单处理 | 卡片内联标签 | 需要肉眼扫描全列表 | — | MEDIUM | 无专门的"异常订单"筛选项（`statusFilters` 只有业务状态，无打印异常/退款待处理维度），排序也不优先异常订单——数量多时容易被淹没在长列表里 |
| 8. 刷新 | 右上角图标按钮 | 1 步 | 1 | LOW | 已在 Phase-03A 验证真实成功/失败反馈，本阶段不重复评估 |
| 9. 查询历史订单 | "历史订单"Tab | Tab+日期+可选搜索+分页 | 2起 | LOW | 结构合理，历史查询本身就该比"今天"更慢一些 |
| 10. 连续处理多单 | 每次动作后 `reconcileAfterOrderAction`→重新排序 | 卡片位置会因重排变化 | — | MEDIUM | 桌台视图结账要经过抽屉+确认弹窗+小票弹窗三层叠加（`settleTableClick`→`a-modal`确认→自动弹出第二个 `a-modal` 小票），关闭小票后才能回到桌台格子选下一桌，共 4 次点击跨 3 层浮层 |

**额外发现（危险动作相邻）**：补打小票和退款按钮可能同时出现在同一行（209-210/393-394），两者视觉上都是同一种红色危险按钮样式，退款不可逆而补打无害，两者视觉不可区分。

**桌台视图 vs 订单列表**：批量动作（"全部接单"、"全部出餐"、结账）**只存在于桌台视图**；订单列表视图没有任何批量操作，每单必须单独点击处理。这是 Jobs 差异导致的合理设计（桌台视图的 Job 就是"整桌处理"），不是缺陷。

## 4. MenuManage 任务链

按 MENU 十项核对当前 `MenuManage.vue`（1576 行）：

| TASK | ENTRY | STEPS | ERROR_RISK | FRICTION |
| --- | --- | --- | --- | --- |
| 1. 找到某道菜 | 无——**主列表确认没有名称搜索**，只有分类标签筛选（44-52） | 滚动/逐个点分类 | LOW | 分类多、单分类菜品多时只能靠滚动，Phase-01 已记录为 P1，本阶段用真实代码位置重新确认仍然成立 |
| 2. 新增菜品 | "加菜品"按钮 | 打开抽屉，必填仅名称+价格，"更多设置"默认折叠 | LOW | 已有渐进披露，符合 OPPO 原则 |
| 3. 改价格 | 无内联编辑，须开完整编辑抽屉 | 开抽屉→改字段→保存，2 次显式点击 | LOW | 抽屉数据取自已加载列表，不发起网络请求，开抽屉本身零延迟 |
| 4. 上架/下架（售罄） | **行内按钮，真正的一键操作**（`toggleSoldOut`，803-812） | 1 步 | LOW | 这是全文件唯一的行内快捷动作，证明"高频动作应该短"在这个文件里是可以做到的 |
| 5. 改库存/售罄 | 同上 | 1 步 | LOW | — |
| 6. 改分类 | 仅编辑抽屉内的下拉框 | 同改价格，2 步 | LOW | — |
| 7. 换图片 | 编辑抽屉内上传框 | 开抽屉→点上传→选文件→**仍需点"保存修改"生效**（toast 明确提示） | LOW | 图片选中即上传，但业务生效仍要等保存，容易让人误以为已经生效 |
| 8. 删除菜品 | "更多"下拉菜单里的危险项 | 开菜单→点删除→`Modal.confirm` | LOW（**故意设计成这样**） | 代码注释（129-130）明确说明：删除挪进"更多"菜单是为了避免和售罄/编辑按钮挤在一起导致忙时误触——这是 ERROR_COST 优先于 CLICK_COUNT 的正确取舍，不是缺陷 |
| 9. 连续编辑多个菜 | 无"保存并编辑下一个" | 每个菜都要开抽屉→编辑→保存→关闭 | LOW | 抽屉是覆盖层不是路由跳转，关闭后列表滚动位置不丢失，但没有链式编辑的快捷方式 |
| 10. 大量菜品查找 | 无分页、无虚拟滚动、只有分类筛选 | 同任务 1 | LOW | 500+ 菜品场景下"查找"本身缺少解法，不是性能问题（渲染没有卡顿证据），是发现路径缺失的问题——本阶段不因为菜品多就启动虚拟滚动/SQL 优化，只记录"没有搜索"这一个真实缺口 |

**额外发现（文案与实现不符）**：分类排序抽屉的说明文案写"拖动排序或用上下箭头调整"（909-918 附近），但模板里**只实现了上下箭头**，没有拖拽处理器——N 个分类要把一个挪到最后，需要点 N-1 次箭头，文案暗示的"拖动"路径根本不存在。

**额外发现（首屏入口竞争）**：页头三个入口"菜品库导入""AI识别导入""加菜品"视觉权重相同，两个"导入"类入口服务的是低频场景（批量导入），却和最高频的"加菜品"并列，挤占第一眼注意力。

## 5. CustomerList 任务链

按 MEMBER 八项核对当前 `CustomerList.vue`（Phase-03D 已修复为真实后端分页，本阶段不重复验证数据真实性，只看操作效率）与 `CustomerDetail.vue`：

| TASK | ENTRY | STEPS | FRICTION |
| --- | --- | --- | --- |
| 1-2. 按手机号/姓名搜索 | 同一个搜索框，占位符已提示两种用法 | 输入+回车/点搜索图标 | 打字不实时触发，需要显式提交，这是合理的（避免过度请求） |
| 3. 加载更多 | 底部按钮，真实翻页 | 1 步/页 | 列表不重置，位置保留 |
| 4. 判断"是不是这个人" | 卡片展示脱敏手机号+会员卡号+状态+来源+"最近到店/还未消费"二元标签 | — | **没有具体的最近到店时间**，只有有/无二元标签；同名两人如果卡号和手机号都记不清，必须点进详情才能确认 |
| 5. 进详情 | 整卡可点 | 1 步 | 无确认，符合预期 |
| 6. 详情页能力 | `CustomerDetail.vue` | — | 手机号/入会时间/最近消费时间在详情页是完整未脱敏的；发券是页内抽屉（3 步：点发券→选券→确认），不离开当前页；查消费记录会跳转到 `/consumptions` |
| 7. 详情返回列表 | 浏览器返回/Tab 导航 | — | **`Layout.vue:3-7` 的 `<router-view>` 没有包 `<keep-alive>`，`customers`/`customers/:id` 是两个独立路由且没有 `meta.keepAlive`**——返回列表会完全重新挂载组件，`keyword`/`page`/`customers`/`loadedKeyword` 全部重置，`onMounted(loadCustomers)` 重新以空关键词、第 1 页发起请求 |
| 8. 连续查多个会员 | 每次都要重新搜索 | 每人 1 次完整搜索循环 | 因为状态本来就被清空，不存在"要不要手动清空搜索框"的问题，但每次都是从零开始搜，无法在同一批候选结果里连续核对多个人 |
| 9. 停用/恢复 | "更多"下拉菜单，与"发券"按钮分属不同控件 | 2 步+确认 | 已经和"发券"物理分开、都有 `Modal.confirm`，误触风险低——不需要治理 |
| 10. 从列表发券 | "发券"按钮跳转到 `/coupons` 带 query 参数 | 1 步（但离开列表） | 与详情页内联发券（第 6 项）是两条不同路径服务同一动作，属于 Phase-04 该记录的行为重复类型，本阶段只记录效率影响：离开列表后同样会因为第 7 项触发状态丢失 |

## 6. Dashboard 任务交接

Dashboard 首页三个真实待办信号的落点核实（`Dashboard.vue`）：

| SIGNAL | CURRENT_DESTINATION | CLICKS_TO_TASK | CONTEXT_PRESERVED | FRICTION |
| --- | --- | --- | --- | --- |
| 待接单 N 单 | `router.push('/orders')`（279） | 1 | 是（进入即看到待接单列表） | 无 |
| 待结账 N 桌 | `router.push({path:'/orders', query:{view:'table'}})`（288） | 1 | 是，且直接带 `view=table`，不需要用户再手动切换 Tab | 无，这是一个已经做对的交接范例 |
| 打印异常 | `loadSystemStatus()`（297，原地重试，非跳转） | 0（不涉及跳转） | — | 合理，打印异常本来就该原地重试确认，不该强行导航到订单页 |
| 桌台异常聚集（扎堆新客） | `router.push('/orders')`（315，未带具体桌台参数） | 1 | 部分——进入订单页后仍需自己找到那张桌 | 轻微，异常场景本身低频，本阶段不作为优先级候选 |
| 智能营销预览 | `InsightCard to="/coupons"` | 1 | 是 | 无 |

**结论**：Dashboard 的交接质量总体良好，两个最高频信号（待接单、待结账）都已经是 1 click 且保留上下文的最佳实践。按 PART_04 指引，**KEEP，本阶段不为 Dashboard 重新设计**。

## 7. 高频任务效率矩阵

| Page | Task | Frequency | Steps | Clicks | Decision Cost | Error Risk | Friction Type | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OrderManage | 发现新订单 | DAILY_HIGH | 0（但易漏看） | 0 | MEDIUM | MEDIUM | F1 | **P0** |
| OrderManage | 拒单 | DAILY_HIGH | 1，零确认 | 1 | LOW | **HIGH** | F6 | **P0** |
| OrderManage | 补打 vs 退款按钮相邻同色 | DAILY_MEDIUM | 1 | 1 | LOW | HIGH | F6 | P1 |
| OrderManage | 异常订单无筛选/不置顶 | DAILY_MEDIUM | — | — | MEDIUM | MEDIUM | F8 | P1 |
| OrderManage | 桌台结账 3 层浮层 | DAILY_HIGH | 4 | 4 | LOW | LOW | F5 | P2（成本较高，见第 12 节） |
| MenuManage | 找一道菜（无搜索） | DAILY_MEDIUM | — | — | MEDIUM | LOW | F1 | **P0（05B）** |
| MenuManage | 改价/改分类须开整表单 | DAILY_MEDIUM | 2 | 2 | LOW | LOW | F3 | P2 |
| MenuManage | 分类排序文案暗示拖拽但只有箭头 | WEEKLY | N-1 | N-1 | LOW | LOW | F2 | P3 |
| MenuManage | 删除藏进更多菜单+确认 | DAILY_LOW | 2+confirm | 2 | LOW | LOW（故意） | — | KEEP，非问题 |
| CustomerList | 详情返回丢失搜索/分页状态 | DAILY_MEDIUM | 重新搜索 | N次 | LOW | LOW | F4/F5/F7 | **P1（05C）** |
| CustomerList | 列表信息不足以精确判断"是不是这个人" | DAILY_MEDIUM | — | — | MEDIUM | LOW | F2 | P2 |
| Dashboard | 待接单/待结账交接 | DAILY_HIGH | 1 | 1 | LOW | LOW | — | KEEP，非问题 |

## 8. Top 10 Frictions（按真实价值排序）

评分方法：`VALUE_SCORE = FREQUENCY × TIME_COST × ERROR_RISK × BUSINESS_IMPACT`（各项 1~5），仅作参考排序，最终判断结合 `IMPLEMENTATION_COST`/`REGRESSION_RISK` 人工调整，不机械采信公式（PART_08 明确要求）。

| RANK | PAGE | TASK | FRICTION | TYPE | VALUE_SCORE | IMPL_COST | REGRESSION_RISK | PHASE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | OrderManage | 新订单发现 | 无高亮，只能靠数字/位置变化发现，同代码库 3 个员工工作台已有现成方案未被复用 | F1 | 5×3×3×4=180 | **1（复用现成 composable 输出）** | **1** | 05A |
| 2 | OrderManage | 拒单 | 零确认且紧邻"接单"主按钮，同文件内"取消待支付"已有确认先例 | F6 | 3×2×5×4=120 | **1（复制同文件已有 Modal.confirm 模式）** | **1** | 05A |
| 3 | OrderManage | 异常订单不置顶/无筛选 | 打印失败/退款待处理订单可能被淹没在长列表 | F8 | 2×3×3×3=54 | 3 | 2 | 05A（评估） |
| 4 | OrderManage | 补打/退款按钮同色相邻 | 无害操作和不可逆操作视觉不可区分 | F6 | 2×1×5×4=40 | 2 | 1 | 05A（评估） |
| 5 | MenuManage | 主列表无搜索 | 500+ 菜品场景查找只能靠滚动+分类 | F1 | 3×4×2×3=72 | 2（数据已全量加载，客户端过滤即可） | 1 | **05B** |
| 6 | OrderManage | 桌台结账 3 层浮层/4 次点击 | 每次结账重复穿越 drawer+2 modal | F5 | 4×3×2×3=72 | 4（涉及浮层结构调整） | 3 | DEFER（05A 观察项） |
| 7 | MenuManage | 改价/改分类须开整表单 | 无内联编辑，对照售罄按钮已证明"一键"可行 | F3 | 3×2×1×2=12 | 3 | 2 | 05B（次要） |
| 8 | CustomerList | 详情往返丢失搜索/分页状态 | 无 `keep-alive`，每次查完一人要重新搜下一人 | F4/F5/F7 | 4×3×1×2=24 | 4（涉及路由/组件缓存架构，非局部改动） | 3 | **05C** |
| 9 | MenuManage | 分类排序文案与实现不符（声称拖拽，只有箭头） | 说明文字承诺了不存在的交互 | F2 | 1×2×1×1=2 | 1（改文案或补实现） | 1 | 05B（低优先级 cheap win） |
| 10 | CustomerList | 列表信息不足以精确辨人 | 只有脱敏手机号+会员卡号，无具体最近到店时间 | F2 | 3×2×1×2=12 | 2 | 1 | 05C（次要） |

## 9. Anti-Feature / 信息降级候选

| ELEMENT | SCREEN_COST | JOB_VALUE | FREQUENCY | DECISION |
| --- | --- | --- | --- | --- |
| MenuManage 页头"菜品库导入"/"AI识别导入"按钮，与"加菜品"同级并排 | 中（占据首屏第一行三分之二宽度） | 低频功能（批量导入） | WEEKLY 或更低 | **DEMOTE**——不建议直接隐藏（仍是真实能力），但不应与最高频的"加菜品"视觉权重相同；本阶段只记录判断，不在 Phase-05 主阶段执行 |
| OrderManage 桌台视图"有历史订单未关联桌台会话"提示行（第 66-68 行附近） | 低（单行文字，条件渲染） | 低频（只在有孤儿订单时出现） | LOW | KEEP——已经是"异常才说话"的正确实现，不需要降级 |
| Dashboard 首单→二单转化率卡片 | 低-中 | 对老板日常操作决策帮助有限（更偏经营分析） | 每次巡店都会看到但不产生动作 | KEEP——不在本阶段范围，Dashboard 首屏信息优先级已在 Phase-01/03B 评估过，本阶段不重新设计 Dashboard |

未发现"老板几乎不用但持续占据首屏"的严重案例——三个核心页面的首屏内容总体上都服务于各自的主 Job，这是 Phase-01/02/03/04 已经打下的底子在起作用，本阶段没有新的降级建议需要立即执行。

## 10. Phase-05A/B/C 拆分

```text
PHASE_05A_PAGE = OrderManage
PHASE_05A_JOB = 新订单不遗漏、异常订单不误判、危险动作不误触——对照 Phase-02 §2.2 已定义的 OrderManage Jobs（"新订单不遗漏，状态不含糊，操作结果可确认"），本阶段发现这条 Job 在"不遗漏"和"操作结果可确认"两端都有真实、低成本可修的缺口
PHASE_05A_CORE_FRICTION = 新订单无视觉高亮（第 8 节 RANK 1）；紧随其后的拒单零确认（RANK 2）
WHY_FIRST = 两项加起来的 VALUE_SCORE 在全部候选里最高，且 IMPLEMENTATION_COST 和 REGRESSION_RISK 都是本次审计里最低的——不是新写业务逻辑，是"复用同代码库里已经跑通、被 3 个姊妹页面验证过的现成模式"（新订单高亮）和"复制同文件里已有的确认对话框模式"（拒单确认）。不选 MenuManage 或 CustomerList 打头阵，是因为它们的最高价值问题成本明显更高（MenuManage 搜索需要新增真实 UI 元素；CustomerList 的状态保留问题需要动路由/组件缓存架构，第 12 节详细说明为什么这个问题分数排不到第一）
```

```text
PHASE_05B_PAGE = MenuManage
PHASE_05B_JOB = 大量菜品场景下，老板/运营能"找到目标菜品"——对照 Phase-01 §2.2 已记录、Phase-03C 状态修复时刻意未处理的 P1 效率缺口
PHASE_05B_CORE_FRICTION = 主列表无名称搜索（第 8 节 RANK 5）
```

```text
PHASE_05C_PAGE = CustomerList
PHASE_05C_JOB = 前台/店员连续核对多个会员时，不需要每次从零重新搜索
PHASE_05C_CORE_FRICTION = 详情页往返丢失搜索/分页状态（第 8 节 RANK 8）——但本阶段的评分显示这个问题的 IMPLEMENTATION_COST 和 REGRESSION_RISK 都明显高于 05A/05B（可能涉及全局路由缓存策略，需要单独评估对其它页面的副作用），因此排在第三，实施前需要在 05C 自己的审计里先确认最小实现方案，不能默认就是"全局加 keep-alive"
```

三个 Phase 分别只改一个页面，不在任何一个阶段同时改订单+菜品+会员。

## 11. Phase-05A AB 方案（新订单发现）

### 方案 A：消费已有的 `isHighlighted` 输出，比照三个员工工作台的实现

`useWorkbenchSync.js` 已经导出 `isHighlighted(id)`（基于 `workbenchSyncCore.js` 内部的 `highlightIds`/`highlightMs` 机制，新订单到达后在 `NEW_ORDER_HIGHLIGHT_MS` 时间窗口内返回 `true`），`FrontdeskWorkbench.vue`、`KitchenWorkbench.vue`、`WaiterWorkbench.vue` 三个文件已经分别用它实现了 `:class="{ 'is-new': isHighlighted(order.id) }"` 边框高亮 + "新"徽章（琥珀色 `#f59e0b`，`FrontdeskWorkbench.vue:233-244`）。方案 A 是把 `OrderManage.vue` 现有的 `const { orders, ... } = useWorkbenchSync({...})` 解构里加上 `isHighlighted`，在列表卡片和桌台格子的对应位置照搬同样的 class 绑定和徽章标记，样式复用已经写好的 `.is-new`/`.new-badge` 规则（可直接抽成共享 CSS 类或按 Touch And Migrate 原则各自保留一份，视触碰时的判断而定）。

- **A 优势**：零新增状态、零新增组件、零新增业务逻辑——`isHighlighted` 已经在生产代码里跑了至少三个页面，风险几乎为零；改动范围严格限定在模板的 class 绑定和一小段 CSS。
- **A 风险**：如果新订单出现在桌台视图里滚动不可见的位置（比如很靠下的格子），仅靠边框高亮仍可能被错过——不能覆盖"完全不在视口内"的极端场景。

### 方案 B：页面顶部增加浮动"新订单"提醒，点击定位到订单

在页面顶部固定位置增加一个类似 toast/banner 的浮动提示，新订单到达时弹出"有新订单！"，点击后自动滚动/跳转到该订单卡片，多个新订单同时到达时聚合显示数量。

- **B 优势**：不受列表滚动位置影响，即使新订单在视口外也一定能被看到，理论上覆盖面比方案 A 更完整。
- **B 风险**：需要新的 UI 元素（浮动提示条/toast 组件）、新的滚动定位逻辑、多订单到达时的聚合与消失时机都需要设计——这已经不是"复用现有能力"，是**新增一块交互面**，改动范围、测试面和潜在副作用（例如和已有的声音提醒 `alert-on-badge`、同步失败横幅叠加时的层级/位置冲突）都明显大于方案 A，不满足 STRICT_RULES 的"最小修改"和"不新增功能"。

### RECOMMENDATION

**方案 A。** 理由：这不是"两个都不错、选一个"的情况——方案 A 是把已经被证明可行、就在同一个代码库里跑着的能力接到最后一个还没接的页面上，方案 B 是在此基础上重新设计一套新交互。按 Touch And Migrate 和"不新增功能"的原则，没有证据表明方案 A 不够用之前，不应该跳到方案 B。如果方案 A 实施后仍有真实商家反馈"新订单在桌台视图里还是容易漏看"，再考虑方案 B 作为独立的后续迭代，而不是在没有证据前就把两者一起做。

## 12. 明确不做什么

防止下一阶段范围膨胀，明确记录本阶段审计到但不安排实施的问题：

1. **OrderManage 桌台结账 3 层浮层**（第 8 节 RANK 6）：真实存在，但合并 drawer+2 个 modal 涉及重新设计确认和小票的呈现方式，IMPLEMENTATION_COST/REGRESSION_RISK 明显高于 05A 已选的两项，本阶段只记录，留给 05A 实施时视证据决定是否纳入，不预先承诺。
2. **CustomerList 的 `keep-alive` 方案**：本阶段判断这需要路由/组件缓存架构层面的改动（`Layout.vue` 的 `<router-view>`、`router/index.js` 的路由 `meta`），可能影响其它页面的挂载/卸载行为，不是 CustomerList 一个文件内的局部改动——05C 立项时需要先做一次小范围的技术方案评估（比如是否只需要在 `sessionStorage` 里存 `keyword`/`page` 并在 `onMounted` 里恢复，而不必引入全局 `keep-alive`），本阶段不预设具体技术方案。
3. **MenuManage 500+ 菜品的虚拟滚动/分页/服务端搜索选型**：按 MENU重点 明确禁止的"因为 500 条就直接启动虚拟滚动"，本阶段只记录"没有搜索"这一个缺口，具体用客户端过滤还是服务端搜索留给 05B 实施时用真实数据规模判断。
4. **Dashboard 重新设计**：第 6 节已判定 KEEP，不安排任何后续动作。
5. **危险动作视觉区分（补打 vs 退款）**：记录在 Top 10（RANK 4），倾向由 05A 顺带评估（同页面、同类问题），但不单独立项，避免把"危险色统一"做成一次跨页面的视觉规范工程。
6. **MenuManage 分类排序文案与实现不符**：低价值但极低成本的"cheap win"，本阶段记录，留给 05B 顺手处理，不单独立项。

## 13. Acceptance

1. **老板每天最高频的后台任务是什么？** 接单/处理订单（OrderManage）是全天候持续发生的最高频任务；菜品维护（改价、上下架）和会员查找是日常但非持续性的高频任务。
2. **OrderManage 最大效率损耗在哪里？** 两处并列：新订单缺少视觉高亮（发现成本）、拒单零确认且紧邻主按钮（错误代价）——都是全代码库已有解法却没接上的真实缺口。
3. **MenuManage 最大效率损耗在哪里？** 主列表没有名称搜索，500+ 菜品场景下"找到目标菜品"只能靠分类筛选+滚动。
4. **CustomerList 最大效率损耗在哪里？** 详情页往返丢失搜索/分页状态，前台连续核对多个会员时必须每次从零开始搜索。
5. **哪些问题是真正高频，而不是设计师觉得"不优雅"？** 本报告排除了"感觉更方便"类结论——第 8 节的每一项都附带真实代码证据（file:line）和基于频率/代价/风险/影响的量化排序，例如 MenuManage 的分类排序"拖拽文案 vs 实际只有箭头"被明确列为低优先级（WEEKLY 频率），没有因为"看起来不专业"就拔高。
6. **哪些动作应该减少步骤？** 新订单发现（0 步但要变成"0 步且更难漏看"，不是加步骤而是加显著性）；拒单动作本身步骤不变，但要加一步确认——这是主动增加步骤换取降低错误代价的例子，不违反"减少步骤"的整体方向，因为它属于第 7 条的例外。
7. **哪些确认动作即使增加一步也必须保留？** 拒单需要新增确认（当前缺失，是缺陷）；菜品删除已有的"更多菜单+二次确认"必须保留，代码注释已经明确说明这是刻意的 ERROR_COST 优先设计，不能因为"步骤多"被误判为需要精简。
8. **有没有低价值信息占据高价值位置？** MenuManage 页头的两个"导入"入口和最高频的"加菜品"视觉权重相同，判定为 DEMOTE 候选，但本阶段不执行，留待 05B。
9. **Phase-05A 为什么应该先做它？** OrderManage 的两个核心摩擦点价值分数最高，且都是"复用同代码库已验证模式"级别的最低成本、最低回归风险实现——没有理由不优先做。
10. **05A 是否可以在不改 API/数据库/状态机情况下完成？** 可以。新订单高亮完全复用前端已有的 `isHighlighted` 计算结果；拒单确认只是在前端加一个 `Modal.confirm` 拦截，不改变 `rejectOrder` 调用的接口或参数。
11. **05B/05C 是否已经明确边界？** 是。05B 边界是 MenuManage 一个文件的搜索能力；05C 边界是 CustomerList 的状态保留问题，且明确要求先做技术方案评估再定具体实现，不预设 `keep-alive`。
12. **是否避免了一次同时重构三个页面？** 是。本阶段（Phase-05 主阶段）没有修改任何业务代码，只产出本报告；后续 05A/05B/05C 三个阶段分别只改一个页面，互不交叉。

```text
FINAL_DECISION=RESULT A: HIGH_FREQUENCY_TASK_EFFICIENCY_BASELINE_READY
TOP_PRIORITY_PAGE=OrderManage
TOP_PRIORITY_JOB=新订单不遗漏、危险动作不误触
TOP_PRIORITY_FRICTION=新订单无视觉高亮（复用现成 isHighlighted 能力）+ 拒单零确认（紧邻主按钮）
PHASE_05A=OrderManage — 新订单高亮 + 拒单二次确认（另评估异常订单可见性、危险按钮视觉区分、结账浮层层级）
PHASE_05B=MenuManage — 主列表名称搜索（另顺手处理分类排序文案）
PHASE_05C=CustomerList — 详情往返状态保留（需先做技术方案评估，不预设 keep-alive）
```

下一阶段进入 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-05A`，只实施 OrderManage 一个页面的最高价值 Job，不重新进行整个 admin-h5 审计。
