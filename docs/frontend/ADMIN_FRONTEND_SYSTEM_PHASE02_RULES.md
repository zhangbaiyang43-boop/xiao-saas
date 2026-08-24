# 开心点单 Admin 前端设计系统 V1.0

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-02
STATUS=ADMIN_FRONTEND_SYSTEM_MINIMUM_EXECUTABLE_RULES
PREVIOUS_PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-01
PREVIOUS_RESULT=ADMIN_FRONTEND_SYSTEM_BLUEPRINT_READY
MODE=RULES_ONLY
RULES_DATE=2026-08-25
REPOSITORY_BASELINE_SHA=f268f7afe915c5d4f456fddac089ccc2a7587a6b
SCOPE=admin-h5
CODE_CHANGE=NO
NEW_PAGE=NO
NEW_COMPONENT_LIBRARY=NO
UI_FRAMEWORK_REPLACEMENT=NO
BIG_BANG_REWRITE=NO
```

## 0. 本文件与现有治理文件的关系

`admin-h5` 已经有一份权威准入合同：[ADMIN_FRONTEND_CONSTITUTION.md](./ADMIN_FRONTEND_CONSTITUTION.md) V1.0。它规定了 UI 框架治理、页面结构合同、状态合同、四个高频业务模块的规则、性能治理、Touch And Migrate 和 MUST NOT 清单，且已经生效。

**本文件不是第二份平行规范，不推翻、不重写 Constitution 任何一条 MUST/MUST NOT。** 本文件是 Phase-01 审计结论到可执行规则的落地，只做 Constitution 尚未细化的四件事：

1. 把 Constitution §3 的 `Content` 层拆解为可执行的 **Business Summary / Main Task Area / Secondary Information** 三段，形成 Phase-01 提出的五层页面模板；
2. 把 Constitution 隐含的“页面要先想清楚 Job”变成**每个页面必须产出的 Jobs 陈述**，含固定输出模板；
3. 把 Phase-01 §6 的组件分级思路变成**可执行的组件准入清单**；
4. 明确 **Ant Design Vue 何时可以直接暴露、何时必须做业务封装**，Constitution 只说了框架优先级，没说封装边界。

权威顺序不变：支付/订单/权限等既有业务合同 > `ADMIN_FRONTEND_CONSTITUTION.md` > 本文件 > 被触摸页面局部实现 > 未触摸历史实现。**任何条款与 Constitution 冲突时，以 Constitution 为准**，并应视为本文件的缺陷，需要修订本文件而不是绕开 Constitution。

## 0.1 本阶段边界

MUST NOT：

1. 不修改任何业务代码；
2. 不开发任何新页面；
3. 不新增组件库；
4. 不替换 Ant Design Vue；
5. 不复制消费者小程序 `member-mini-client` 的 UI、转化布局或视觉规则；
6. 不发起一次性重构；
7. 不为不存在的重复场景预先抽象组件；
8. 不为了统一而统一。

允许：制定规范、制定模板、制定准入规则。本文件的产出是评审标准，不是实现。

---

# 1. 设计目标

Phase-01 把 `admin-h5` 当前成熟度定为 **L2，64/100**：工程底座（74/100）可靠，但产品和设计系统尚未形成一致执行能力。五个主要问题（对应 Phase-01 §2、§10.1）：

1. 状态真实性不足——加载失败被显示为空、默认零值或“运行中”；
2. 页面缺少 Jobs 驱动——信息和动作不是按“老板要做什么”组织，而是按接口和数据库对象排列；
3. 组件没有业务治理——19 个本地组件中 9 个无消费者，同时又缺少“该不该抽组件”的标准（[ADMIN_FRONTEND_DESIGN_AUDIT.md §2.4](./ADMIN_FRONTEND_DESIGN_AUDIT.md)）；
4. 信息密度偏高——高频页面把老板决策所需信息和低频配置、说明文字混在同一优先级；
5. 不同页面存在重复实现——同一语义（卡片、状态条、空态、按钮）在不同页面各写一遍（[ADMIN_FRONTEND_DESIGN_AUDIT.md §2.3](./ADMIN_FRONTEND_DESIGN_AUDIT.md)）。

本阶段目标不是让后台变漂亮，而是让这五个问题变成**可以被评审的规则**，使得：

- 商家老板：更快发现问题，更快完成任务，更低理解成本；
- 开发者：新页面有规则可循，旧页面触摸时有边界可维护，评审有统一标准而不是各自判断。

约束前提不变：在现有 **Vue 3 + Ant Design Vue** 基础上建立约束，不是建立新设计体系、不是新组件库、不是新 UI 框架。

---

# 2. Admin 产品原则

## 2.1 ADMIN PAGE PRINCIPLE

任何新增页面或被需求触摸的旧页面，评审前 MUST 先用固定模板回答“老板/店长/店员为什么打开这个页面”：

```text
页面：
用户：      老板 / 店长 / 前台 / 服务员 / 后厨（可多选，须分主次）
任务：      Jobs — 在什么经营场景下，需要完成什么任务
成功标准：  Outcome — 完成后得到什么确定结果，如何判断“做完了”
核心动作：  Next Action — 页面必须提供的最短路径动作
禁止展示：  与此 Job 无关、会稀释注意力或制造虚假确定性的内容
```

`核心动作`必须是具体交互（如“接单”“改价并保存”“查看未确认到店会员”），不能写成“查看数据”这类不可验收的目标。`禁止展示`必须写具体项，不能空着——空着视为未完成该页面的 Jobs 陈述。

## 2.2 五个高频页面的 Jobs 陈述

以下内容延续 Phase-01 §4.1 的核心 Job，补齐`核心动作`与`禁止展示`两列，作为后续 Touch And Migrate 的验收基线：

| 页面 | 用户 | 任务 | 成功标准 | 核心动作 | 禁止展示 |
| --- | --- | --- | --- | --- | --- |
| Dashboard | 老板 / 店长 | 开店或巡店时，快速确认今天经营结果、当前异常、下一步动作 | 异常先被看到，今日核心结果可信，动作可直达 | 处理待办、跳转异常来源 | 无法由真实数据证明的“运行中/正常”；与今日决策无关的历史趋势置顶 |
| OrderManage | 前台 / 店长 | 订单进入和流转时，快速接单、出餐、结账、处理打印或支付异常 | 新订单不遗漏，状态不含糊，操作结果可确认 | 接单、出餐、结账、补打、退款 | 把营销、套餐说明或经营统计堆在接单主路径前面 |
| DishManage | 店长 / 老板 | 供应、价格或商品信息变化时，快速找到目标菜品并完成维护 | 可搜索定位，供应状态明确，保存结果可信 | 搜索定位、改价、售罄/恢复、上下架 | 加载失败显示为空菜单；找不到目标菜品时无任何引导 |
| MemberManage | 老板 / 店长 | 需要服务或经营会员时，快速找到人、理解价值并执行合适动作 | 数据可达、分层可理解、动作可追踪 | 搜索会员、发券、查看消费价值 | 前端切片伪装成分页；无法触达 100 条以后的真实会员 |
| Marketing | 老板 | 投入优惠成本时，知道系统在做什么、带来什么结果、是否需要调整 | 运行状态真实，成本和效果可解释，决策有下一步 | 确认当前档位、查看效果、调整或暂停 | 无法证明的默认“自动运行中”；有数据无建议的效果报表 |

新增页面 MUST 先填好本表结构对应的一行，再进入设计和评审；不属于以上五页的页面，沿用 2.1 模板单独产出。

## 2.3 OPPO Less but Better（B 端版本）

沿用 Phase-01 §4.2，不是复制消费者端视觉，而是约束 B 端复杂度：

- MUST 减少无效信息：正常状态静默，异常和待处理优先；
- MUST 减少无效操作：同一任务只保留一个主入口，危险动作与高频动作分离；
- MUST 减少无效状态：不展示无法由真实数据证明的“运行中”“正常”“0”；
- SHOULD 渐进披露：高级参数、低频配置和审计信息按需展开；
- SHOULD 默认路径覆盖大多数老板，专业能力放在次级入口；
- MUST NOT 以删掉必要信息为“极简”，准确性和可追溯性优先于视觉简洁。

信息优先级固定为：`异常和风险 > 当前待办 > 今日/当前结果 > 趋势与解释 > 低频配置 > 系统说明`。

---

# 3. 页面模板规范：Admin Page Layout V1

## 3.1 五段结构

```text
Page Header
    ↓
Business Summary
    ↓
Main Task Area
    ↓
Secondary Information
    ↓
Feedback Area
```

这是对 Constitution §3（`PageHeader → Content → Action → Feedback`）的可执行细化，不是新结构：`Business Summary` 和 `Main Task Area` 都属于 Constitution 的 `Content`；`Action` 不再作为独立分区，而是内嵌在 `Main Task Area`（贴近被操作对象，与 Constitution §3.3“主动作靠近对象”一致）；`Secondary Information` 是新拆出的低优先级信息区，用于承接原本会挤进 Content 的说明性内容。这不要求所有页面 DOM 顺序一致，也不要求视觉相同，只要求信息位置可预测。

| 区域 | 必须回答 | 规则 |
| --- | --- | --- |
| Page Header | 页面名称是什么？页面目标是什么？主操作是什么？ | 标题稳定；主操作最多一个强调级别；返回路径可预测；窄屏不得并列堆放多个同级小按钮 |
| Business Summary | 现在结果如何？有什么异常？ | 只放与本页 Job 直接相关的经营指标；失败 MUST NOT 显示默认值，需落入第 4 节的 `error`/`unknown` |
| Main Task Area | 我来这里主要处理什么？ | 承载主列表、工作台或核心表单；动作贴近对象；同一操作区域只有一个最高优先级动作 |
| Secondary Information | 还有什么辅助信息，但不影响当前任务判断？ | 低频配置、说明文字、历史记录、装饰性内容；MUST NOT 排在 Main Task Area 之前，MUST NOT 抢占异常和主动作的注意力 |
| Feedback Area | 系统是否真的完成？ | loading、empty、error、success、unknown 明确且互斥，见第 4 节 |

## 3.2 适用范围

**必须使用五段结构**：Dashboard、OrderManage、DishManage、MemberManage、CouponCenter/MarketingEffectiveness 等承载核心经营任务的一级和高频二级页面。

**不强制使用**：

- 纯配置/设置类页面（门店信息、账号设置等）：可以只保留 `Page Header → Main Task Area(表单) → Feedback`，没有可汇报的经营指标时不得为凑结构编造 `Business Summary`；
- 详情/编辑类弹层或子页面（菜品编辑、会员详情）：遵循 Constitution §3 的 `PageHeader → Content → Action → Feedback`，`Business Summary` 与 `Secondary Information` 的划分不强制,但 `Feedback` 仍是 MUST；
- 角色工作台（前台/服务员/后厨）：MAY 用“待办列表”替代 `Business Summary`，因为一线岗位的核心信息本身就是待处理任务，不是经营指标。

模板 MUST 允许业务差异：订单桌台工作台不得为了套用本模板被改造成普通卡片列表；设置页不得被要求长得像 Dashboard。

---

# 4. 状态合同规范：Admin State Contract V1

本节是对 Constitution §4 的执行细则，新增 `unknown` 作为独立状态（Constitution 原文用 `error` 承载“无法确认”，Phase-01 §5.2 进一步区分了“确认失败”与“无法证明”两种情形，本节把两者都落到可执行标准）。

所有页面 MUST 区分五种状态，且互斥：

## Loading

- 展示什么：保留任务上下文（标题、已输入内容、已知的旧数据），必要时用骨架屏或局部 loading 指示正在处理。
- 禁止什么：MUST NOT 提前展示尚未确认的结果；MUST NOT 允许同一动作重复提交而无法识别。

## Success

- 展示什么：后端或既有业务合同确认完成后的最终结果，并同步更新相关页面状态；风险越高的操作，结果 SHOULD 保持越久可确认（不能只是一闪而过的 toast）。
- 禁止什么：MUST NOT 保存失败仍保持“已保存”外观；MUST NOT 只因前端本地状态已改变就宣告成功。

## Empty

- 什么时候出现：请求**成功**，且**确认**没有符合条件的数据。
- 如何引导：说明为空的具体范围（例如“当前分类下没有菜品”而不是“暂无数据”）；因筛选条件导致的为空 MUST 提供清除筛选或返回路径；MUST 结合 2.2 节的 Job 给出下一步（例如会员为空态引导去发展会员，而不是留白）。

## Error

- 如何展示：明确写出“发生了什么”，不得用空态、默认值或颜色代替文字；已有可信旧数据时 MAY 保留但 MUST 标注“上次数据/可能过期”。
- 如何恢复：可恢复的失败 MUST 提供就地重试，不强制用户离开当前页面重新进入。

## Unknown（新增，Constitution 状态合同的补充）

- 定义：系统当前**无法证明**真实状态（例如营销策略是否在生效、打印机是否在线、首次请求前的默认档位）。
- 展示：MUST 使用“未知/未确认”等明确文字，MUST NOT 借用成功绿或错误红假定结果，也 MUST NOT 用一个看似正常的默认值替代。
- 何时触发：请求尚未返回、返回但无法解析出确定结论、依赖的外部设备/服务无法确认状态时。

## 4.1 明确禁止（对应 Phase-01 P0 问题清单）

- 禁止：接口失败显示空数据。菜品加载失败 MUST 显示 `error`，MUST NOT 落入“还没有菜品”的空态（[ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md §4.1-E](./ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md)）。
- 禁止：未知状态显示正常。营销预览失败时 MUST NOT 保留“自动运行中”默认文案（[ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md §4.1-C](./ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md)）；打印机在首次请求返回前 MUST 是 `unknown`，MUST NOT 默认异常或默认正常（同 §4.1-D）。
- 禁止：HTTP 200 但业务 `code` 失败被当作成功处理。页面 MUST 显式检查业务 code，不能只依赖 axios 是否抛出异常。
- 禁止：手动刷新失败仍提示“已刷新”或吞掉错误（[ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md §4.1-A](./ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md)）。

---

# 5. 组件治理规范：Component Governance Rule

## 5.1 组件分级

**Level 1：基础组件**

- 范围：Button、Card、Form、Input、Select、Table/List、Modal/Drawer、Empty、Loading/Skeleton、Alert、Message。
- 来源：MUST 直接使用 Ant Design Vue 已有能力。
- MUST NOT 再包装一套只改颜色、圆角或命名的基础组件；MUST NOT 用原生 HTML 或 CSS 复制这些能力（[ADMIN_FRONTEND_CONSTITUTION.md §2.3](./ADMIN_FRONTEND_CONSTITUTION.md)）。

**Level 2：通用业务组件**

- 定义：表达稳定业务语义，服务两个及以上真实业务场景，而不是视觉容器。
- 已证明的 Level 2 组件（[ADMIN_FRONTEND_DESIGN_AUDIT.md §2.4](./ADMIN_FRONTEND_DESIGN_AUDIT.md)）：`PageHeader`（19 个页面消费）、`StatCard`、`InsightCard`、`WorkbenchSyncBar`、`AssistedOrderSheet`、`PickupNoPicker`、`TabBar`。这些组件 MUST 保留并按 Touch And Migrate 治理，不得因为“看起来是历史代码”被顺手重写。
- 示例：`StatusTag`（订单/菜品/会员状态标签，语义一致但当前分散在各页面自绘）属于 Level 2 候选，尚未提取，见 5.3 准入流程。

**Level 3：页面组件**

- 只服务单一页面，禁止过度抽象。例如某页面独有的筛选面板、某表单的专属校验展示。
- 出现相似结构但只有一个真实消费者时，MUST 保持 Level 3，不得提前抽成 Level 2。

**待核实/疑似失活组件（不进入分级，单独处理）**：`ListState`、`CustomTable`、`CustomCheckbox`、`CustomDatePicker`、`CustomRadio`、`PaginationBar`、`DataCard`、`NavBar`、`RefreshList` 共 9 个组件当前无静态消费者，`ListState` 还使用了未安装的 Element Plus 标签（[ADMIN_FRONTEND_DESIGN_AUDIT.md §2.4](./ADMIN_FRONTEND_DESIGN_AUDIT.md)）。MUST NOT 在新页面中引用；MUST NOT 直接删除；进入 Phase-04 组件治理阶段单独审计动态依赖后再处理。

## 5.2 组件准入条件

新增或将 Level 3 提升为 Level 2 组件，MUST 同时满足：

1. **真实业务重复**：至少两个真实页面或两个稳定业务场景需要同一语义，不是“看起来像”；
2. **状态一致**：loading/empty/error/success/unknown 的合同一致，不只是外观相似；
3. **交互一致**：触发方式、反馈位置、确认要求一致；
4. **维护成本下降**：抽取后能减少重复维护或降低出错概率，而不只是减少几行模板代码；
5. **业务决策仍在页面/业务层**：组件本身不得内嵌 API 调用决策或业务规则判断，只表达语义和状态。

不满足以上任一条时，MUST 保持 Level 3 或不抽取。

## 5.3 组件治理流程

```text
发现重复 → 确认业务语义一致 → 盘点消费者 → 定义状态合同 → 小范围复用 → 验证 → 扩大使用
```

禁止从“看起来相似”直接跳到全局抽象。5.1 节列出的 `StatusTag` 等候选，需要在下一次真实触摸相关页面时按本流程验证，不在本阶段直接创建。

---

# 6. Ant Design Vue 使用规则

## 6.1 何时直接使用

以下场景 MUST 直接使用 Ant Design Vue 组件，不做业务封装：

- 纯展示、无重复业务规则的表单、弹窗、抽屉（如设置页的字段编辑）；
- 一次性、单页面使用的 Table/List/Modal，且状态合同不跨页面复用；
- 通用反馈类组件：Message、Notification、Alert、Skeleton、Empty 的默认用法。

## 6.2 何时需要业务封装

当 Ant 组件承载的不是通用交互，而是**特定业务对象的状态机、批量规则或跨页面复用的语义**时，MUST 封装为 Level 2/3 业务组件，不得直接对外暴露裸的 Ant 组件 API。判断标准：

- 该组件是否需要理解订单状态机、支付/退款结果、库存/售罄语义等业务规则？是 → 必须封装。
- 该组件是否在多个页面需要保持完全一致的状态表达（例如“新订单”高亮规则）？是 → 必须封装。
- 该组件是否涉及不可逆或高风险动作（退款、批量下架、删除）？是 → 必须封装以强制二次确认和结果反馈，不能依赖每个调用方各自记得加确认。

**示例（对应 Phase-01 §1.7 超大文件问题的方向性约束，不是本阶段的重构授权）**：

- 订单页面 MUST NOT 直接暴露一个裸的 `a-table` 承载新订单/历史订单/桌台的全部逻辑；触摸订单页面时，状态呈现和批量动作 SHOULD 沿着 `OrderList`（列表与状态呈现）、`OrderAction`（接单/出餐/结账/退款等动作与确认）这类业务边界收敛，而不是继续在页面模板里堆叠 `a-table` + 内联判断。
- 菜品列表的售罄/上下架状态 SHOULD 通过统一的业务组件表达（见 5.1 的 `StatusTag` 候选），不是每个使用方各自拼接文字和颜色。

本节只定义判断标准和方向，具体拆分动作 MUST 遵循第 8 节 Touch And Migrate，不在本阶段执行。

---

# 7. 高频页面设计规则

## P0：Dashboard + OrderManage

### Dashboard

- 老板第一眼 MUST 知道今天经营状态：核心指标、异常提醒、待处理事项三者必须同屏可见，异常和待处理优先于趋势。
- 首屏顺序固定为：可行动异常 → 今日结果 → 经营解释；正常状态 SHOULD 静默，不占据首屏注意力。
- 每张卡片 MUST 能回答“老板看完要不要做事”，答不了的内容降级到 Secondary Information 或移出首屏。
- 禁止：纯数据报表式罗列，不带异常判断和下一步指向。

### OrderManage

- 目标是快速处理订单，不是浏览订单。MUST 突出新订单、异常订单（同步失败/打印失败/支付异常）、状态流转。
- 新订单 MUST 与历史订单、已处理订单在视觉和结构上可区分，不能靠用户自己数状态字段。
- 禁止：让店员在忙时阅读复杂表格或深层筛选才能找到需要处理的订单。
- 不改变订单状态机、API 或业务流程；本条规则只约束呈现和信息优先级。

## P1：DishManage、MemberManage

- 遵循 Constitution §5.2、§5.3 的业务规则（菜品 error/empty 分离、大规模可搜索；会员真实分页、真实可达）；
- 设计上先保证 Jobs 陈述（2.2 节）能被满足，即“找到目标菜品/会员”和“理解会员价值”，再讨论视觉呈现；
- 何时引入搜索、分页、虚拟化等具体方案，MUST 由真实任务和性能数据决定，本文件不预先指定实现。

## P2：Marketing

- 遵循 Constitution §5.4：自动营销状态必须真实，无法证明时显示 `unknown`（第 4 节）；
- 效果页 SHOULD 建立“运行状态 → 投入 → 结果 → 建议动作”的解释链，不能只给数字不给判断依据；
- Vant 页面按 Touch And Migrate 迁移，不做一次性 Ant 替换（第 8 节）。

---

# 8. 性能规则关联

本节只定义标准，不在本阶段执行优化，具体预算和测量方法以 [ADMIN_FRONTEND_CONSTITUTION.md §6](./ADMIN_FRONTEND_CONSTITUTION.md) 为权威，不重复展开。

- 每个页面 MUST 有明确的 Loading / Error / Empty 表达（见第 4 节），这是性能问题和状态问题的共同前提——用户分不清“慢”和“坏”时，两者都无法诊断。
- 大列表（订单、菜品、会员）MUST 考虑分页、搜索或渐进加载中的至少一种真实方案，MUST NOT 用“一次性加载全部数据再前端筛选”掩盖可达性问题。
- 禁止：没有测量数据时的性能优化。任何优化动作 MUST 先有 Constitution §6 定义的基线和预算,再讨论方案。

---

# 9. Touch And Migrate 策略

沿用 [ADMIN_FRONTEND_CONSTITUTION.md §7](./ADMIN_FRONTEND_CONSTITUTION.md) 的强制策略，本文件不新增例外：

```text
NEW_CODE=MUST_COMPLY          — 新页面/新交互 MUST 遵守本文件 + Constitution 全部规则
TOUCHED_LEGACY=MIGRATE_IN_SCOPE — 修改旧页面 MUST 迁移本次需求直接触摸的结构、状态、Job 陈述
UNTOUCHED_LEGACY=MAY_REMAIN     — 未触摸页面 MAY 保持现状，不因本文件生效而被判定为“违规”
BIG_BANG_REWRITE=MUST_NOT       — 禁止以合规为由发起页面/组件的一次性重写
```

每次触摸 MUST 说明：触摸范围、保留的旧行为、对照第 2.2 节 Jobs 陈述和第 4 节状态合同的验证结果、未处理的债务。

---

# 10. 后续实施路线

Phase-02（本文件）交付最小可执行规则，不授权实施。下一步：

| Phase | 目标 | 入口 |
| --- | --- | --- |
| Phase-03 | 按 Constitution §9 和 Phase-01 §7 的 P0→P1→P2 波次，对 OrderManage、Dashboard 先做状态真实性 Touch And Migrate（第 4 节 `error`/`unknown` 修复），再处理菜品/会员可达性，最后处理营销状态真实性 | 每次 Touch 前先按第 2.1 节产出 Jobs 陈述，验收对照第 8.3 节（Constitution）与本文件第 2/4 节 |
| Phase-04 | 组件治理：验证 5.1 节的 9 个疑似失活组件是否存在动态依赖，处理有结论后再清理或转正 | 按 5.3 节流程执行，不在 Phase-03 顺手处理 |
| Phase-05 | 性能优化：仅在 production 样本满足 Constitution §6 基线门槛后启动 | 当前无启动条件（沿用 Phase-01 §9 结论） |

Phase-03 启动前 MUST 确认：需求是否真实触摸到对应页面；不得为了执行本文件而主动新增“治理型”需求去触摸未被业务需要变更的页面。

---

## ACCEPTANCE：验收回答

1. **未来 admin 页面是否有统一设计规则？** 有。Constitution 定义准入边界，本文件定义 Jobs 陈述模板、五段页面结构、状态合同的可执行细则、组件三级准入和 Ant 封装边界，两者共同构成同一套规则，无冲突。
2. **页面开发是否可以按照规则执行？** 可以。第 2.1/2.2 节给出固定输出模板和五个高频页面的示例填写；第 3 节给出适用范围和不适用场景；开发者可以直接对照评审，不需要额外解释。
3. **组件是否有准入标准？** 有。第 5 节定义了三级分级、五条准入条件（缺一不可）和治理流程，并列出了当前已证明的 Level 2 组件与 9 个待核实组件，避免凭感觉抽象或凭感觉复用。
4. **状态是否可以避免失真？** 可以避免已知的失真模式。第 4 节把 Constitution 的四态状态合同扩展为五态（新增 `unknown`），并针对 Phase-01/高频页面审计中已发现的具体证据（菜品空菜单、营销假运行、打印机默认状态、刷新假成功）逐条列为禁止项，后续 Touch And Migrate 可直接对照检查。
5. **是否支持长期演进？** 支持。规则建立在现有 Vue3 + Ant Design Vue 之上，不引入新框架或平行体系；组件和页面结构允许业务差异；Touch And Migrate 保证旧页面不因新规则生效被判违规，新增复杂度只在真实重复出现时才被吸收为规则或组件，避免过度设计。

```text
FINAL_DECISION=RESULT A: ADMIN_FRONTEND_SYSTEM_RULES_READY
```

本结论只授权后续按 Touch And Migrate 使用这套规则评审需求，不授权任何业务代码、页面、组件或性能优化变更。Phase-03 的具体页面改造需要独立的实施任务和验收证据。
