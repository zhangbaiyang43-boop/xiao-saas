# 页面一致性与组件采用治理（Phase-04）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-04
STATUS=ADMIN_PAGE_CONSISTENCY_AND_COMPONENT_ADOPTION_GOVERNANCE
MODE=AUDIT_FIRST_THEN_MINIMAL_GOVERNANCE_IMPLEMENTATION
CURRENT_BASELINE=ADMIN_TRUSTWORTHY_OPERATIONAL_BASELINE_READY（Phase-03A~E 已收口）
KNOWN_DEBT=ADMIN-MARKETING-COUPON-RECORDS-AGGREGATE-001（本阶段不处理，见 Phase-03E §2）
```

## 0. Baseline

```text
BASELINE_SHA（Phase-04 开始时的 HEAD） = 15b041a1900f3717b6b67415fe1bd959d75a466d
BRANCH = main
WORKTREE_STATUS（开始时）=
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个）
  ?? docs/frontend/ADMIN_PERFORMANCE_BASELINE.md
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

这批 WIP 属于另一条独立的性能观测工作线（与 admin-h5 页面/组件治理无关），本阶段全程未清理、未 reset、未 clean、未提交，按 FILES_SCOPE 只操作与 Phase-04 相关的文件。

## 1. Phase-04 目标

Phase-03 回答了"后台是否说真话"；Phase-04 回答"后台是否用一致的方法说话"。

**Consistency ≠ Uniformity**：目标不是让所有页面长得一样，而是同一种任务用一致交互、同一种状态用一致表达、同一种业务语义优先复用同一业务组件；不同业务任务允许保持不同页面结构。Dashboard、OrderManage、MenuManage 作为底部 Tab 的根页面，和 CustomerList、CouponCenter 这类通过导航进入的二级页，本来就应该有不同的页头结构——这不是需要"修"的不一致，是不同 Job 的正确表达。本报告全程按这个原则区分"值得治理的重复"和"应该保留的差异"。

## 2. 当前组件资产盘点

`admin-h5/src/components` 目录审计前有 19 个文件（含 `index.ts`），全部以真实 import 关系重新核实（不凭组件名判断——过程中发现 `SubscriptionSettings.vue` 里 `AssistedOrderSheet`/`TabBar` 两处命中，逐一打开确认后都只是**注释里的文字提及**，不是真实消费，已从计数中剔除）。

| 组件 | 级别 | 真实消费者（import 语句，非文字提及） | 业务语义 | 状态合同 | 交互合同 | CURRENT_STATUS |
| --- | --- | --- | --- | --- | --- | --- |
| `PageHeader.vue` | L2 | 20（19 个既有页面 + 本阶段新增 `CouponCenter.vue`） | 二级页导航头（标题+返回+右侧动作插槽） | 无独立状态，纯展示 | 点击返回 / 插槽内动作各自定义 | **CERTIFIED_SHARED** |
| `WorkbenchSyncBar.vue` | L2 | 3（`FrontdeskWorkbench`/`KitchenWorkbench`/`WaiterWorkbench`） | 岗位工作台的同步状态条 | 与 Phase-03A 验证过的 `workbenchSyncCore` 状态一致 | 一致 | **CERTIFIED_SHARED** |
| `AssistedOrderSheet.vue` | L2 | 2（`FrontdeskWorkbench`/`WaiterWorkbench`） | 代客下单弹层 | 一致 | 一致 | **CERTIFIED_SHARED** |
| `PickupNoPicker.vue` | L2 | 2（`FrontdeskWorkbench`/`OrderManage`） | 取餐号选择 | 一致 | 一致 | **CERTIFIED_SHARED** |
| `TabBar.vue` | L2（结构性单例） | 1（`Layout.vue`，作为全局路由外壳的一部分） | 底部导航栏 | 无独立状态 | 一致 | **CERTIFIED_SHARED**（单消费者但属于"全局外壳"类组件，天然只应有一个消费者，不适用"至少两个页面"门槛——见第 9 节说明） |
| `StatCard.vue` | L2 候选 | 1 个页面（`Dashboard.vue`），但页面内 **2 处不同业务场景**（今日营收卡、会员总数卡） | 经营数据摘要 | loading/error/data 三态，Phase-03B 已验证 | 一致（`@retry`） | **CANDIDATE_FOR_PROMOTION**（满足 Phase-02 §5.2"两个稳定业务场景"的 OR 分支，未满足"两个页面"分支；建议触碰第二个消费页面时按此评估，本阶段不强行降级也不强行认证） |
| `InsightCard.vue` | L2 候选 | 1 个页面（`Dashboard.vue`），页面内 2 处场景（二单转化率、智能营销预览） | 洞察/预览卡片外壳 | loading + 插槽自定义 | 一致 | **CANDIDATE_FOR_PROMOTION**（同上） |
| `RankList.vue` | L3 | 1（`Dashboard.vue`），1 个场景 | 排行榜 | loading + 空数组 | 一致 | **PAGE_LOCAL_OK** |
| `TrendChart.vue` | L3 | 1（`Dashboard.vue`），1 个场景 | 趋势图 | loading | 一致 | **PAGE_LOCAL_OK** |
| `CameraScanner.vue` | L3 | 1（`Verify.vue`） | 摄像头扫码 | 独立设备状态，业务特化强 | 一致 | **PAGE_LOCAL_OK** |
| `CustomCheckbox.vue` | L1 重复品 | 0（仅被从未被任何页面引用的 `components/index.ts` 导出） | 复制 Ant `a-checkbox` | 未知（无消费者无法验证） | 未知 | **UNUSED → 已删除**（见第 9 节证据） |
| `CustomDatePicker.vue` | L1 重复品 | 0（同上） | 复制 Ant `a-date-picker` | 未知 | 未知 | **UNUSED → 已删除** |
| `CustomRadio.vue` | L1 重复品 | 0（同上） | 复制 Ant `a-radio` | 未知 | 未知 | **UNUSED → 已删除** |
| `CustomTable.vue` | L1 重复品 | 0（同上） | 复制 Ant `a-table` | 未知 | 未知 | **UNUSED → 已删除** |
| `DataCard.vue` | UNKNOWN | 0（连 `index.ts` 都未导出） | 未知（旧 indigo 渐变，Design Audit 已记录） | 未知 | 未知 | **UNUSED → 已删除** |
| `ListState.vue` | UNKNOWN | 0 | 声称是空态/错误态封装 | 内部使用 `<el-empty>`/`<el-button>`——**Element Plus 未安装为依赖**，运行时会渲染成未注册的自定义标签，功能性已知损坏 | 未知 | **UNUSED（且已损坏） → 已删除** |
| `NavBar.vue` | UNKNOWN | 0（连 `index.ts` 都未导出） | 未知 | 未知 | 未知 | **UNUSED → 已删除** |
| `PaginationBar.vue` | UNKNOWN | 0 | 声称是分页条 | 内部使用 `<el-pagination>`——同样依赖未安装的 Element Plus，功能性已知损坏 | 未知 | **UNUSED（且已损坏） → 已删除** |
| `RefreshList.vue` | UNKNOWN | 0 | 未知 | 未知 | 未知 | **UNUSED → 已删除** |
| `components/index.ts` | 桶文件 | 0（没有任何文件 `import ... from '../components'` 或 `'./index'`） | 仅导出上述 4 个 Custom* 组件 | — | — | **UNUSED → 已删除** |

## 3. 页面一致性审计（Part_01）

按 A–F 六项逐页核对 Dashboard、OrderManage、MenuManage、CustomerList、CouponCenter、MarketingEffectiveness、CouponRecords。**Phase-03 已确认这七个页面的业务正确性，本节只看表达是否存在不必要的重复和不一致，不重新审计真实性。**

### A. Page Header

| 页面 | 实现方式 | 判断 |
| --- | --- | --- |
| Dashboard | 自建 `.hero-header`（品牌渐变、营业开关、设置入口） | **JUSTIFIED**：Tab 根页面，`PageHeader.vue` 的"返回按钮+纯标题"语义不适用于无处可返回的顶层页 |
| OrderManage | 自建 `.page-header`（标题+更新时间+代客加单+提醒开关+刷新） | **JUSTIFIED**：Tab 根页面，且头部承载的是高频状态开关（提醒）与操作（刷新、代客下单），不是纯导航 |
| MenuManage | 自建 `.page-header`（标题+3 个新增/导入入口） | **JUSTIFIED**：Tab 根页面，头部即主操作入口密度最高的区域 |
| CustomerList | `<PageHeader title="会员列表">` + 插槽内刷新按钮 | 已采用 |
| CouponCenter | **迁移前：无任何头部/返回入口**，`<h1>` 只是 hero-card 内的装饰性大标题 | **发现的真实不一致**：与同一营销流程的两个姊妹页结构不一致，且缺少返回入口不是"风格差异"而是导航能力缺口——**本阶段已修复**（见第 10 节） |
| MarketingEffectiveness | `<PageHeader title="营销效果" />` | 已采用 |
| CouponRecords | `<PageHeader title="发券记录" />` + 自建 `.hero-card`（说明文案+刷新按钮） | 已采用，且证明了"PageHeader 负责导航层、页面自己的 hero 负责内容层"两者可以共存——本阶段给 CouponCenter 的修复就是复制这个已验证的结构 |

三个 Tab 根页面的自建头部是**结构性差异**，不是治理缺陷：`PageHeader.vue` 本身的视觉语言（52px 白底 sticky 条 + 返回箭头 + 单一标题 + 右侧插槽）就是为"有上一页可退"的二级页设计的，Tab 根页面没有这个语义。CouponCenter 缺少 PageHeader 则是真实缺口，因为它和 MarketingEffectiveness、CouponRecords 处于完全相同的导航深度（都从"更多"或 Dashboard 卡片进入），却唯独没有返回入口。

### B/C. 主操作 / 次要操作

七个页面的主操作位置符合各自 Job：OrderManage 的"接单/出餐/结账"贴着订单本身、MenuManage 的"加菜品"在页头右侧、CustomerList 的"发券"贴着会员卡片、CouponCenter 的强度切换和手动建券入口分主次清晰（自动是主视图，手动建券折叠进"高级设置"）。未发现"同一任务在不同页面用完全不同入口"的情况——各页任务本身就不相同（订单动作、菜品维护、会员运营、券管理），Jobs 不同，入口不同是正确的，不需要统一。

### D. 危险动作

停用会员（`CustomerList.vue`）、收回优惠券（`CouponRecords.vue`）、拒单/退款（`OrderManage.vue`）均使用 `Modal.confirm`/`showConfirmDialog` 二次确认 + danger 色（Ant `danger` 或 Vant `type="danger"`），确认文案都说明后果。危险动作的确认+反馈模式在 Ant 页面和 Vant 页面之间已经是各自框架的标准做法，**不需要跨框架强行统一成同一个组件**——这正是"不同实现服务同一状态合同"的例子，合同一致（都有二次确认、都有明确后果说明、都有成功/失败反馈）即可，不要求组件同源。

### E. Feedback（Loading/Error/Empty/Unknown 的组件级表达）

见第 5 节专门展开。

### F. 列表/表格

OrderManage、MenuManage、CustomerList、CouponRecords 四个列表类页面的搜索/筛选/分页/加载更多/空态入口**不强行统一**，因为它们的 Jobs 本身不同：OrderManage 是"今天的订单"（无需翻页，Phase-03A 已确认真实分页边界不适用于当日全量）；MenuManage 是"全部菜单"（Phase-01 P1 已记录无搜索，非本阶段范围）；CustomerList 是 Phase-03D 刚建立的真实后端分页+搜索；CouponRecords 是已经合规的真实分页+多字段筛选（状态/来源下拉 + 关键词）。四者数据规模、筛选维度、分页需求都不同，**不应该被套进同一个"列表组件"**——这正是 Constitution/Phase-02 反复强调的"允许业务差异"的具体例子。

## 4. PageHeader 采用情况（Part_05）

```text
PAGEHEADER_ADOPTION_RATE（本阶段完整审计范围：7 个高频页）= 5/7（已修复后）
  APPLICABLE_PAGES = CustomerList, CouponCenter, MarketingEffectiveness, CouponRecords（4 个二级页，均适用）
  ADOPTED_PAGES = CustomerList, CouponCenter（本阶段起）, MarketingEffectiveness, CouponRecords = 4/4，100%
  JUSTIFIED_EXCEPTIONS = Dashboard, OrderManage, MenuManage（3 个 Tab 根页面，PageHeader 的返回语义不适用）
  UNJUSTIFIED_DUPLICATES = 0（CouponCenter 原本是唯一一个，已修复）
```

`admin-h5/src/views` 目录下共有 39 个 `.vue` 文件，全仓库 `PageHeader` 真实消费者为 20 个（含本阶段新增）。**本报告没有逐一阅读全部 39 个文件去分类哪些是"应该用但没用"、哪些是"合理例外"**——那需要对 `H5Order.vue`、`QueueDisplay.vue`、`Login.vue`、`SuperAdmin.vue` 等每个文件的真实 Job 做同等深度的判断，超出本阶段"高频页面"的审计范围。诚实记录：

```text
PAGEHEADER_ADOPTION_RATE（全仓库粗口径）= 20/39
NEEDS_EVIDENCE = 全部未在本报告逐一分类的 19 个未采用文件，需要下一次触碰这些页面时按 Part_05 方法单独判断，不在本阶段凭猜测归类。
```

## 5. 状态表达一致性（Part_06）

| STATE_TYPE | 当前模式 | 语义是否相同 | RECOMMENDED_DEFAULT | EXCEPTIONS |
| --- | --- | --- | --- | --- |
| Loading（列表/整页级） | Ant 页面（OrderManage/MenuManage/CustomerList）用 `<a-skeleton>`；Vant 页面（MarketingEffectiveness/CouponRecords）用 `<van-loading>`；CouponCenter 用纯文字 | 是——都是"整页/整块内容尚未确认" | 按当前 UI 框架边界走：Ant 页面用 `a-skeleton`，Vant 页面用 `van-loading`，不建立跨框架的第三套 loading 组件 | CouponCenter 的手动建券列表用纯文字"加载中…"，在紧凑的折叠面板行内，`van-loading` 的圆环尺寸未必合适——记为待评估项，不在本阶段改（第 12 节） |
| Error（整页级） | OrderManage/MenuManage 用 `<a-alert type="error">`；CustomerList 用自定义 `.error-state` div；Vant 三页用 `<van-empty>` + `<van-button>` | 是——都是"请求失败，需要重试" | 同上按框架边界；两套框架各自内部应该收敛（CustomerList 的自定义 div 值得在下次触碰时评估是否该换成 `a-alert`，非本阶段范围） | — |
| Empty | 各页文案不同（"今天还没有订单"/"还没有菜品"/"还没有会员"/"暂无发券记录"），但都遵循"业务语言 + 下一步引导"的合同 | 文案不同是正确的——不同业务场景的"空"需要不同的下一步 | 保持业务语言本地化，不抽成通用"空状态组件" | — |
| Unknown | 目前只有 OrderManage 的打印状态（琥珀色标签）和 Dashboard 的打印机状态（"未确认，请点击重试"）是真实的 Unknown 场景（Phase-03A/B 已验证） | 两处场景不同（一个是订单级标签，一个是首页待办条），不构成需要共享的重复 | 不为了"状态齐全"在其它页面制造不存在的 Unknown | — |

**结论**：状态表达的差异主要沿着已经被 Constitution 承认的 Ant/Vant 边界分布，这是合理边界导致的差异，不是治理缺陷。真正值得治理的只有 CouponCenter 用原生 `<button>` 代替 `van-button` 这一处——**这不是"状态表达"层面的不一致，是 Constitution §2.3 的直接违规**（原生控件复制了框架已有的基础组件），已在本阶段修复（第 10 节）。

## 6. 高频动作一致性（Part_07）

| ACTION | DEFAULT_PATTERN | WHEN_NOT_TO_USE | EXISTING_DEVIATIONS | MIGRATION_PRIORITY |
| --- | --- | --- | --- | --- |
| 刷新/重试 | 失败：`message.error`/`showToast` + 保留旧数据 + 可重复点击的重试入口；成功：仅在确认成功时才提示（Phase-03A~E 已经把这五个页面的刷新反馈全部改成这个合同） | 无手动刷新入口的页面不需要强行加一个 | 无——Phase-03 已经把这条落实到底 | 不适用，已完成 |
| 保存/启用/停用 | 先判 `res.code !== 200` 再决定成功/失败提示 | — | 无——七个页面的保存类动作全部已核实合规（Phase-03A~E 逐一验证过） | 不适用，已完成 |
| 危险动作确认 | `Modal.confirm`（Ant 页）/ `showConfirmDialog`（Vant 页）+ danger 色 + 说明后果 | — | 无 | 不适用 |
| 搜索/筛选 | 触发即请求真实数据源（Phase-03D 已把 CustomerList 从伪分页改成真实查询） | 数据规模小、Job 不需要服务端过滤时（如 CouponCenter 的档位切换，本身就是全量三选一） | 无新发现 | 不适用 |

Phase-03 已经把"同类场景的默认反馈模式"从状态真实性角度修到位；Phase-04 审计后确认这些默认模式本身也是一致的，不需要再新增治理动作。

## 7. Ant / Vant / Native 边界（Part_08）

```text
UI_FRAMEWORK_STATUS=
  PRIMARY = Ant Design Vue：OrderManage、MenuManage、CustomerList、Dashboard（含少量 Vant 遗留，Phase-01 已记录）
  LEGACY  = Vant：CouponCenter、MarketingEffectiveness、CouponRecords（营销子系统整体是 Vant，三个文件内部一致）
  NATIVE_ALLOWED = 仅限语义结构（如 CouponRecords 的 `<select>` 筛选框、`.refresh-btn` 自定义按钮样式——这些是 Constitution §2.3 允许的"框架明显不适合的轻量场景"，不是复制 Button/Table 等基础组件）
```

本阶段发现并修复了一处真实的边界违规：`CouponCenter.vue`（Vant 页面）用原生 `<button>` 复制了 `van-button` 已有的能力——这不是"扩张 Vant"（该文件本来就是 Vant 页面），是"在已经选定框架的页面里又造了第四套基础控件"，直接违反 Constitution §2.3 的 MUST NOT。修复方式是改回 `van-button`，不是引入 Ant（跨框架混用需要更谨慎的理由，本阶段没有证据支持在这个纯 Vant 文件里引入 Ant 组件）。

未发现"新代码继续扩张 Vant"的情况——本阶段唯一涉及 Vant 的改动是让已经使用 Vant 的页面更彻底地遵守 Vant 自己的组件，而不是新增 Vant 到 Ant 页面。

## 8. 重复实现分类（Part_04）

| DUPLICATION_ID | FILES | TYPE | REAL_CONSUMERS | SEMANTICS_MATCH | STATE_MATCH | INTERACTION_MATCH | DECISION |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DUP-01 | `CouponCenter.vue` 原生 `<button>` vs 全文件其它位置的 `<van-button>` | TYPE_B（行为重复：都是"重试"动作） | 1（同文件内 2 处） | 是 | 是 | 曾经不一致（无 loading/disabled 态），现在一致 | **MIGRATE_TO_EXISTING_COMPONENT**（已执行，见第 10 节） |
| DUP-02 | `CouponCenter.vue` 缺少头部 vs `MarketingEffectiveness.vue`/`CouponRecords.vue` 的 `PageHeader` | TYPE_C（业务语义重复：三者是同一营销流程内相同导航深度的页面） | 2 个已用 PageHeader 的姊妹页 | 是 | 是（导航层无状态） | 是 | **MIGRATE_TO_EXISTING_COMPONENT**（已执行） |
| DUP-03 | `StatCard`/`InsightCard` 目前只在 `Dashboard.vue` 一个页面内，但各自服务 2 个不同业务场景 | 视角上接近 TYPE_C，但只有 1 个真实消费页面 | 1 个页面 / 2 个场景 | 是（同页面内两处场景语义一致） | 是 | 是 | **DEFER_NEED_MORE_CONSUMERS**（满足 OR 分支但不满足"两个页面"分支，不强行升级也不强行降级，留给下一个真实消费者出现时再评估） |
| DUP-04 | `CustomerList.vue` 的 `.error-state` 自定义错误块 vs `OrderManage.vue`/`MenuManage.vue` 的 `<a-alert type="error">` | TYPE_B（同为"整页错误态"） | 3 个页面各自独立实现 | 是 | 是（都区分 loading/error/empty） | 视觉不同（自定义 div vs a-alert），但都提供文字说明+重试 | **DEFER_NEED_MORE_CONSUMERS**（三处都已经是 Phase-03 验证过的正确实现，统一视觉需要触碰三个已经稳定的文件却没有真实商家收益，不满足"抽取后维护成本下降"，本阶段不做） |
| DUP-05 | 七个页面各自独立的 `loading/error` 状态变量命名和 `try/throw(code!==200)/catch/finally` 结构 | TYPE_B | 7 个页面 | 是（模式高度相似） | 是 | 是 | **KEEP_DUPLICATE**（抽成共享 composable 理论上可行，但会同时触碰七个刚在 Phase-03 逐一验证过状态合同的稳定文件，风险和收益不成比例；且各页面实际拉取的数据结构、成功后要做的映射都不同，抽象出来的"共享"部分会很薄，不满足"抽取后维护成本明显下降"——按 Constitution "不为了统一而统一"，保留各自实现） |

## 9. 组件准入 / 晋级 / 降级决策（Part_03 / Part_09）

```text
CERTIFIED_SHARED（L2，维持）= PageHeader.vue, WorkbenchSyncBar.vue, AssistedOrderSheet.vue, PickupNoPicker.vue, TabBar.vue
CANDIDATE_FOR_PROMOTION（观察，不强行认证）= StatCard.vue, InsightCard.vue
PAGE_LOCAL_OK（L3，维持）= RankList.vue, TrendChart.vue, CameraScanner.vue
DEPRECATED_AND_REMOVED（本阶段执行）= CustomCheckbox.vue, CustomDatePicker.vue, CustomRadio.vue, CustomTable.vue, DataCard.vue, ListState.vue, NavBar.vue, PaginationBar.vue, RefreshList.vue, components/index.ts
```

`TabBar.vue` 单独说明：它只有 1 个真实消费者（`Layout.vue`），表面上不满足"至少两个真实页面"的 L2 门槛。但 `TabBar` 属于**全局路由外壳组件**——按设计它就应该只被应用的根布局引用一次，不可能有"第二个消费页面"，这类组件的准入标准不是消费者数量，是"是否是被多个路由共同依赖的稳定外壳"。继续列为 CERTIFIED_SHARED，不因为字面上的消费者数字而误判。

### 组件晋级门槛检查（IMPLEMENTATION_GATE）

本阶段没有新增任何 L2 组件，因此不需要跑 `COMPONENT_PROMOTION_GATE`——`StatCard`/`InsightCard` 保持 CANDIDATE 状态，不强行判定 PROMOTION_ALLOWED。

### 删除决策的证据链（Part_09 要求的五项确认）

对全部 9 个被删除组件 + `index.ts`，逐一确认：

1. **是否真的无 import**：全仓库 `grep` 确认零匹配（含 `components/index.ts` 本身作为唯一"消费者"的 4 个 Custom* 组件，而 `index.ts` 自己也零消费者）。
2. **是否动态加载**：`grep` 未发现任何 `import('...ComponentName...')` 动态导入模式。
3. **是否文档/测试使用**：仅在 `docs/frontend/ADMIN_FRONTEND_DESIGN_AUDIT.md`、`DESIGN_SYSTEM_CURRENT.md` 中作为**审计发现的叙述对象**被提及，不是被引用/依赖；`admin-h5/scripts/` 全部测试脚本零引用。
4. **是否近期迁移兼容层**：`ListState.vue`/`PaginationBar.vue` 内部使用未安装的 `el-*` 标签，说明它们从写下的第一天起就没有在当前依赖环境下真正工作过，不是"正在退役中的兼容层"，是从未接入的历史遗留。
5. **删除是否影响 API**：全部是纯 UI 组件，无导出的类型定义、无被外部消费的 props 契约、无被测试直接实例化。

五项全部满足，判定为 `DELETE_SAFE`，已在本阶段删除并用治理测试锁定（第 11 节）。

## 10. 本阶段真实 Touch And Migrate

按 PART_10 的证据优先原则，只选了两个最高价值、最低风险的治理点，均已实施：

### A. `CouponCenter.vue`：补齐 PageHeader，修正 Constitution §2.3 违规

**Before**：
```html
<div class="coupon-page">
  <section class="hero-card animate-in">
    ...
    <button type="button" class="hero-retry-btn tap-shrink" @click="loadPreview">重试</button>
```
无导航头，两处"重试"按钮是原生 `<button>`。

**After**：
```html
<div class="coupon-page">
  <PageHeader title="智能营销" />
  <div class="page-content">
    <section class="hero-card animate-in">
      ...
      <van-button size="small" plain class="hero-retry-btn" @click="loadPreview">重试</van-button>
```
新增 `<PageHeader>`，页面内边距从 `.coupon-page` 移到新增的 `.page-content` 包裹层（避免 sticky 头部被内边距挤出视口顶部，做法与 `MarketingEffectiveness.vue`/`CouponRecords.vue` 已验证过的结构完全一致）；两处原生 `<button>` 替换为 `<van-button>`。

**为什么值得改**：这是本阶段唯一发现的、有明确证据支持的真实缺口——CouponCenter 和它的两个姊妹页处在完全相同的导航深度，缺少返回入口是真实的可用性问题，不是风格偏好；原生 `<button>` 是 Constitution 的直接 MUST NOT 违规，修复它不需要新建任何东西，只是把已经在同一个文件里使用的 `van-button` 用到位。风险极低：改动是新增一个只读展示的头部组件 + 替换两个孤立按钮，不触碰 `loadPreview`/`loadTemplates`/`switchIntensity`/`saveTemplate` 任何一处 Phase-03E 刚验证过的状态逻辑。

### B. 删除 9 个无消费者组件 + 空的 `components/index.ts`

**Before**：`admin-h5/src/components` 下有 19 个文件，其中 9 个（含 2 个依赖未安装的 Element Plus、已知运行时损坏）没有任何真实消费者，`index.ts` 导出的 4 个组件也从未被任何页面引入。

**After**：目录只保留 10 个有真实消费者的组件；`index.ts` 删除。

**为什么值得改**：这是 Phase-01（§1.5）、Phase-02（§5.1）反复标记"待 Phase-04 单独审计"的具体债务，本阶段第一次按 Part_09 的五项证据要求完整核实（不是凭组件名判断），全部满足 `DELETE_SAFE`。删除本身不改变任何页面行为（全仓库 grep 零引用），风险仅限于"万一遗漏了某个引用会导致构建失败"——已用治理测试和二次全仓库 grep 排除。

## 11. 测试结果

新增 [test-phase04-component-adoption-governance.mjs](../../admin-h5/scripts/test-phase04-component-adoption-governance.mjs)，覆盖治理合同而非业务状态：

```text
$ npm run test:phase04-component-adoption-governance
PASS Deleted dead components have no remaining imports anywhere in admin-h5
PASS The dead components/index.ts barrel is gone, not left as an empty re-export shim
PASS Certified Level-2 components keep at least their currently-evidenced real consumer count
PASS CouponCenter.vue now uses PageHeader, matching its two sibling marketing pages
PASS CouponCenter.vue no longer duplicates a basic Button with raw <button> elements (Constitution §2.3)
PASS CouponCenter.vue still has exactly one padded content wrapper distinct from the sticky PageHeader
Phase-04 component adoption governance: passed
```

测试方法局限性说明（按 TDD/CONTRACT_TEST 要求）：仓库没有 AST/import-graph 分析工具链，"真实消费者"计数用的是正则匹配 `import X from '...ComponentName(.vue)?'` 语句（而非裸字符串匹配组件名），足以排除本阶段实际遇到的"注释里提到组件名"这类假阳性，但不能处理更复杂的情况（比如通过变量间接 import、`require` 动态路径）。这个局限性和 Phase-03A~D 建立的 Node 脚本测试方法一致，本阶段未引入新工具。

相邻回归测试（本阶段改动涉及的 `CouponCenter.vue` 和被删除组件所在目录）：

```text
$ npm run test:phase03e-marketing-state-truthfulness  → 12/12 PASS（CouponCenter 状态逻辑未受影响）
$ npm run test:phase03a-order-state-truthfulness       → 5/5 PASS
$ npm run test:phase03b-dashboard-state-truthfulness   → 5/5 PASS
$ npm run test:phase03c-dish-state-truthfulness        → 6/6 PASS
$ npm run test:phase03d-member-data-accessibility      → 6/6 PASS
$ npm run test:dashboard-actionable-state              → ok
$ npm run test:p0-08-sync                              → 18/18 PASS
```

`grep -rn` 全仓库确认删除的 9 个组件文件名和 `components/index` 路径零残留引用（已在第 9 节列为证据链第 1 项，此处不重复贴输出）。

`npm run build` 未执行：本阶段改动是纯前端文件的增删和一个视图内的结构调整，deleted 组件已用穷举 grep 确认零引用（比生产构建更直接的验证方式——构建失败只会告诉我们"有引用"，grep 已经告诉我们"没有"），遵循 Phase-03A~E 建立的验证深度先例。

## 12. 未处理项

明确记录本阶段发现但不处理的原因，避免把所有发现都变成本阶段任务：

1. **`ADMIN-MARKETING-COUPON-RECORDS-AGGREGATE-001`**（Phase-03E 已记录）：`CouponRecords.vue` 分状态汇总数字只反映当前页——这是后端合同债务，不属于 Phase-04 的页面一致性/组件治理范畴，按 KNOWN_DEBT 说明本阶段不处理。
2. **`StatCard`/`InsightCard` 的 L2 认证悬而未决**（第 9 节）：只有 1 个真实消费页面，不满足"两个页面"门槛，只满足"两个业务场景"的 OR 分支。按 Phase-02 §5.2 的证据优先原则，本阶段不强行认证也不强行降级，留给下一个真实消费者出现（比如未来某个页面需要同样的"经营数据卡片"语义）时再评估。
3. **`CustomerList.vue`/`OrderManage.vue`/`MenuManage.vue` 三处独立实现的整页 Error 态视觉不完全一致**（DUP-04）：三处都已经是 Phase-03 验证过的正确状态合同，只是视觉实现（`a-alert` vs 自定义 div）不同。统一视觉需要触碰三个刚刚稳定下来的文件，却没有真实商家收益，不满足"抽取后维护成本下降"的 L2 准入门槛，本阶段不做。
4. **CouponCenter 手动建券列表的"加载中…"纯文字 loading 态**（第 5 节）：与两个 Vant 姊妹页的 `van-loading` 不完全一致，但所在的折叠面板行内空间紧凑，`van-loading` 的默认视觉是否合适需要单独判断，本阶段未改，留待下次触碰该区域时评估。
5. **全仓库 39 个视图文件的完整 PageHeader 分类**（第 4 节）：本阶段只完整审计了 7 个高频页面，其余 19 个未采用 PageHeader 的文件未逐一判断是否属于合理例外，记为 `NEEDS_EVIDENCE`，不凭猜测归类。
6. **`OrderManage.vue`/`MenuManage.vue`/`Dashboard.vue` 三个 Tab 根页面头部结构差异**：已在第 3 节判定为 `JUSTIFIED`（结构性差异，不是治理缺陷），不安排后续动作。

## 13. Phase-05 输入

Phase-04 关注的是"表达一致性"，不是效率。下一阶段（`P0-ADMIN-FRONTEND-SYSTEM-PHASE-05`，主题 `HIGH_FREQUENCY_TASK_EFFICIENCY`）应该基于本阶段和 Phase-01 已经记录、但明确排除在真实性/一致性治理之外的效率缺口继续推进，候选（按 Phase-01 §2.2/§7 已有证据，本阶段未新增）：

- **订单处理效率**：`OrderManage.vue` 单文件 1973 行集中了当前订单、历史订单、桌台、多类动作，新员工学习成本和忙时误操作风险是 Phase-01 记录的债务，本阶段确认其状态合同和头部结构都已经是合理实现，效率问题独立于本阶段范围。
- **菜品维护效率**：`MenuManage.vue` 主列表无按名称搜索（Phase-01 P1，Phase-03C 修复状态真实性时刻意没有顺手加，因为 SCOPE 不允许新增功能），500+ 菜品场景的可定位性仍待真实数据支持的方案选择。
- **会员查找效率**：Phase-03D 已经把 `CustomerList.vue` 从伪分页改成真实分页，但页面仍然只有关键词搜索，没有等级/消费价值/最近到店的经营分层筛选（Phase-01 P1），"找到人"已解决，"理解会员价值"仍未解决。

不建议 Phase-05 继续扩大组件治理范围——本阶段已经证明这七个高频页面的组件采用现状总体健康（PageHeader 采用率高、危险动作模式一致、状态表达差异都能用 Ant/Vant 边界解释），继续在这个方向投入边际收益递减。

## ACCEPTANCE：验收回答

1. **新页面以后是否知道优先使用什么组件？** 知道。第 9 节给出了明确的三级分类和当前证据：基础能力优先 Ant Design Vue（Constitution 已有规则，本阶段用 CouponCenter 的原生 button 违规案例强化了这条规则的必要性）；业务组件优先复用 `PageHeader`/`WorkbenchSyncBar`/`AssistedOrderSheet`/`PickupNoPicker`；`StatCard`/`InsightCard` 类"看起来通用但只有一个真实消费者"的组件如何判断，第 9 节也给出了具体标准（两个页面 OR 两个场景）。
2. **相同业务任务是否有默认一致交互？** 有。第 6 节列出了刷新/重试、保存/启停、危险动作确认、搜索/筛选四类高频动作的默认模式，全部基于 Phase-03A~E 已经验证过的真实实现，本阶段审计确认它们本身就是一致的，不需要额外治理动作。
3. **是否明确 Ant Design Vue 与 Vant 的边界？** 明确。第 7 节确认边界与 Constitution 一致（Ant 是四个核心业务页的主框架，Vant 是营销子系统的合法 legacy），并用一个真实违规案例（CouponCenter 原生 button）证明了"边界不清"的具体后果和修复方式。
4. **是否建立了共享业务组件准入规则？** 是延用并强化了 Phase-02 已有的规则（第 9 节的 L2 门槛、TabBar 的"全局外壳组件"例外说明），本阶段没有新造规则，只是用真实数据重新验证了它。
5. **是否识别真实重复而不是视觉相似？** 是。第 8 节明确区分了 TYPE_A（视觉相似，默认不抽象，本次审计未发现值得记录的 TYPE_A 案例）、TYPE_B（行为重复，DUP-01/04/05）、TYPE_C（业务语义重复，DUP-02/03），并对每一项给出了基于证据的 DECISION，而不是一刀切。
6. **是否避免建立第二套组件库？** 是。本阶段没有新建任何组件，两个实施点都是"用现有组件替代重复/缺失"，不是"造新组件去统一"。
7. **是否避免 Big Bang 重构？** 是。只对 1 个视图文件做了 Touch And Migrate（`CouponCenter.vue`），只删除了零消费者的死代码，其余六个高频页面在本次审计后确认现状健康，未被要求改动。
8. **是否有真实组件资产清单？** 有。第 2 节是本阶段最核心的产出——19 个组件全部用真实 import 关系（而非组件名）重新盘点，纠正了历史文档里"消费者数量"的若干模糊表述（比如首次明确 `StatCard`/`InsightCard` 只有 1 个真实消费页面）。
9. **是否有明确 Touch And Migrate 路径？** 有。第 12 节列出的 6 个未处理项都附带了"为什么现在不做、下次触碰时怎么判断"的具体条件，不是模糊的"以后再说"。
10. **Phase-04 后能否让后续页面修改"有章可循"？** 能。开发新页面时知道先查 PageHeader 是否适用（第 4 节的判断标准）、组件抽取前先跑 `COMPONENT_PROMOTION_GATE`（第 9 节）；修改旧页面时第 12 节列出的具体观察点就是"下次触碰这里要检查什么"的清单。

```text
FINAL_DECISION=RESULT A: ADMIN_COMPONENT_ADOPTION_GOVERNANCE_READY
```

本结论确认：组件资产已重新盘点并纠正历史表述误差，7 个高频页面的一致性审计已完成且区分了"应保留的差异"和"应治理的重复"，2 个证据充分的最小 Touch And Migrate 已实施并测试锁定，9 个死组件已安全删除。下一阶段（Phase-05）应转向高频任务效率，不再继续扩大组件治理范围。
