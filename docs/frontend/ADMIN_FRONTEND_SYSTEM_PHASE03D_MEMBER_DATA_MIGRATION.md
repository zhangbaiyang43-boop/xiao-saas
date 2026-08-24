# 会员数据可达性 Touch And Migrate（Phase-03D）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03D
STATUS=MEMBER_MANAGE_DATA_ACCESSIBILITY_MIGRATION
PREVIOUS_PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03C
REFERENCE=ADMIN_FRONTEND_CONSTITUTION.md V1.0, ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md, ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md
REPOSITORY_BASELINE_SHA=f0cdd33b120645d4ac58a35d447fe6be2c891608
SCOPE=admin-h5/src/views/CustomerList.vue（数据获取与状态展示逻辑）
BUSINESS_CODE_CHANGE=YES（分页/搜索请求方式与失败态处理，见第 4/5 节）
API_CHANGE=NO（后端已支持，只读核实，未修改 saas-base）
BACKEND_CONTRACT_BLOCKED=NO
NEW_MEMBER_TAG=NO
NEW_MARKETING_FEATURE=NO
MEMBERSHIP_RULE_CHANGE=NO
POINTS_LOGIC_CHANGE=NO
PERFORMANCE_OPTIMIZATION=NO
FULL_PAGE_REWRITE=NO
```

## 0. 文件名映射说明

延续 Phase-03C 的模式，REFERENCE 用的产品名是 "MemberManage"，仓库里没有 `MemberManage.vue` 文件。实际承载会员列表 Job 的是 `admin-h5/src/views/CustomerList.vue`（迁移前 222 行）。本报告和新增测试全部针对这个真实文件；下文继续用"会员管理/MemberManage"指代产品身份，代码引用统一写 `CustomerList.vue`。

## 1. MemberManage Jobs 分析

沿用并落实 [ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md §2.2](./ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md) 已定义的 MemberManage Jobs：

- **用户**：老板 / 运营人员。
- **任务**：需要服务或经营会员时，快速找到人、理解价值并执行合适动作。
- **成功标准**：老板知道当前真实会员数量、数据是否完整加载、是否存在异常、是否可以继续筛选和运营。
- **核心动作**：搜索会员、发券、查看消费价值。
- **禁止展示**：前端切片伪装成分页；无法触达 100 条以后的真实会员。

这一页处在"用户消费 → 会员沉淀 → 会员资产 → 营销复购"链路的资产入口位置。如果老板看到的会员总数是假的（比如后台显示 100，实际 10000+），会直接影响他对私域规模、复购潜力和是否值得投入营销成本的判断——这不是视觉问题，是会算错账的问题。

## 2. 当前数据访问审计

逐条核对当前 `CustomerList.vue`（迁移前）源码：

### 2.1 数据获取方式 —— 不符合：前端一次拉取后本地切片

```js
async function loadCustomers() {
  ...
  const params = { page: 1, page_size: 100, skip: 0, limit: 100 }
  ...
}
```

`page` 永远是 `1`，`page_size`/`limit` 永远是 `100`——**这不是一个真实的分页参数，是一次性拉取"前 100 条"的固定请求**，且没有任何代码路径会改变这几个数字去请求第 2 页。

### 2.2 总会员数量 —— 不符合：用 `array.length` 冒充总数

响应体从未被读取 `total` 字段。模板里唯一的"总数"相关文案是`已显示全部 {{ customers.length }} 位会员`——`customers.length` 是**这一次固定请求返回的行数（最多 100）**，不是数据库里真实的会员总数。10000 个会员的门店，这里永远只会显示"100"或更少。

### 2.3 分页真实性 —— 不符合：纯前端"展开"操作

```js
const pageSize = ref(30)
const visibleCustomers = computed(() => customers.value.slice(0, pageSize.value))
// 模板
<a-button @click="pageSize += 30">加载更多</a-button>
```

点"加载更多"只是把 `pageSize`（本地展示行数上限）从 30 加到 60、90……**不会产生任何新的网络请求**，只是把已经在内存里的、最多 100 条数据里更多的部分显示出来。一旦 100 条全部展开完，第 101 条以后的会员在这个页面上永远不可达，无论怎么点"加载更多"。

### 2.4 搜索 —— 部分符合，但受同一个 100 条上限约束

`params.search`/`params.keyword` 确实带着关键词发到了后端（不是前端 `.filter()` 模拟），这一点是真实查询。但请求本身仍然固定 `page_size: 100`——如果某个关键词在数据库里匹配超过 100 条，第 101 条以后的匹配结果同样不可达，且页面没有任何提示"还有更多匹配结果"。

### 2.5 筛选 —— 不适用，当前无筛选 UI

当前页面除了关键词搜索框，没有等级、积分、消费金额等筛选控件。这是 [ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md §2.2](./ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md) 记录的"缺少可执行分层"P1 效率问题，不是本阶段的状态真实性问题；STRICT_RULES 也明确不允许本阶段新增会员标签/营销能力。**结论：无筛选 UI 可审计，本阶段不新增。**

### 2.6 加载失败 —— 不符合，且发现一个业务失败分支遗漏

```js
if (res.code !== 200) {
  resultStatus = 'error'
  message.error(res.msg || '会员加载失败')
  customers.value = []
  return   // 注意：这里没有 loadError.value = true
}
```

模板已经有 `v-else-if="loadError"` 分支，说明这个页面曾经是打算做失败态区分的，但**业务级失败（HTTP 200、`code!==200`）这条分支唯独忘了把 `loadError.value` 置真**——只有网络异常（`catch` 块）才会正确进入错误态。业务失败时 `loadError` 仍是初始的 `false`，`customers.value` 又被清空为 `[]`，于是模板顺着 `v-else-if="customers.length === 0"` 落入空态"还没有会员，去生成桌贴码让顾客扫码入会吧"——这正是 CURRENT_AUDIT 第 6 条要防的"失败=没有会员"，只是它只发生在业务失败这一条路径上，网络异常路径原本是对的。

### 2.7 空状态 —— 依赖 2.6 的修复才能区分

`customers.length===0` 目前同时对应"真的没有会员""业务失败""确认为空"三种情况中的两种（业务失败会误判为空），必须先堵住 2.6 的漏洞。

## 3. 数据真实性问题（后端契约核实）

在动代码之前，先只读核实了后端是否真的支持真实分页——如果不支持，本阶段必须停止并提出 `BACKEND_CONTRACT_CHANGE_REQUEST`。核实结论（`saas-base/app/api/v1/customers.py`、`customer_service.py`、`app/core/pagination.py`）：

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 真实分页 | **支持** | `page`/`page_size` 转换为 `skip`/`limit`，`normalize_pagination` 后传给 `CustomerService.list_customers(skip=, limit=)`，服务层用真实 `.offset(skip).limit(limit)` |
| 真实总数 | **支持** | `select(func.count()).select_from(query.subquery())`——真正的 `COUNT(*)`，不是 `len(rows)`，随 `data.total` 返回 |
| 真实搜索 | **支持** | `search` 参数映射为 `phone=search, name=search`，服务层是 `WHERE phone LIKE %search% OR name LIKE %search%` 的真实 DB 过滤 |
| 响应封装 | `{code, msg, data: {items, total, skip, limit, page, page_size}}` | `success_response(data=build_page(...))` |
| 单页上限 | `PAGE_MAX_LIMIT=200` | 请求的 `page_size:100` 在这个上限内，不会被截断 |

**结论：后端分页能力充分，本阶段不需要提出合同变更，可以直接进入实现。** 这与 SCOPE/STRICT_RULES 里"如果发现 API 无法支持真实分页，停止开发，提出 BACKEND_CONTRACT_CHANGE_REQUEST"的前置条件相符——检查过了，条件不成立，因此正常推进。

## 4. 修改方案

在 `saas-base` 完全不改的前提下，把 `CustomerList.vue` 从"一次拉 100 条 + 本地展开"改成"真实向后端请求分页"：

1. 新增真实分页状态：`total`（后端真实总数）、`page`（当前已加载到第几页）、`loadedKeyword`（当前展示数据对应的关键词，用于第 6 节的失败态判断）；删除伪分页状态 `pageSize`/`visibleCustomers`。
2. `loadCustomers()`（首次加载/刷新/换关键词搜索）始终请求真实第 1 页，把业务失败和网络失败统一到同一个 `throw → catch` 路径，堵住 2.6 发现的遗漏分支；成功时把 `total.value` 设为响应体的真实 `data.total`。
3. 新增 `loadMore()`：请求 `page.value + 1`，成功后把新行 `concat` 到已有列表并推进 `page`，失败不回退已加载数据、不推进页码（原地可重试）。
4. 模板"加载更多"按钮的判断条件从 `visibleCustomers.length < customers.length`（比较两个本地数组）改为 `customers.length < total`（比较已加载行数和后端真实总数）。
5. 失败态拆成两支：有旧数据且关键词未变 → 常�称警示条 + 继续显示旧数据（Constitution §4"保留仍可信的旧数据"）；没有旧数据，或者旧数据是**上一个关键词**搜出来的 → 独立错误态，不能把旧关键词的结果冒充成这次搜索的结果。

选择这个范围而非更大改动的原因：STRICT_RULES 明确禁止新增会员标签、营销功能、CRM 设计、批量操作、性能优化和整页重构；本阶段的 Job 只是"让老板相信会员数据"，这只需要分页和状态判断变得真实，不需要改变页面的信息架构或交互形态。

## 5. 分页合同变化

| 维度 | Before | After |
| --- | --- | --- |
| 请求参数 | 固定 `{page:1, page_size:100, skip:0, limit:100}`，永不变化 | `{page, page_size:30}`，`page` 首次为 1，翻页时真实递增 |
| 总数来源 | `customers.length`（当次请求返回的行数，上限 100） | `data.total`（后端 `COUNT(*)` 的真实总数，无上限） |
| "加载更多" | 本地 `pageSize += 30`，展开内存里已有数据，不产生网络请求；触达上限=100 | `loadMore()` 真实请求下一页，`concat` 追加；触达上限=后端真实总数 |
| 搜索 | 关键词发到后端，但仍固定 `page_size:100`，第 101 条以后的匹配结果不可达且无提示 | 关键词发到后端，且真实分页对搜索结果同样生效；"还有 N 位"文案基于真实 `total` |
| 业务失败 | 遗漏 `loadError.value = true`，落入假空态 | 与网络失败走同一 `throw/catch` 路径，必定进入错误态 |
| 失败时旧数据 | 无论哪种失败都清空为 `[]` | 保留旧数据；关键词未变时显示"当前显示的是上次数据"，关键词已变时不冒充成新结果 |

## 6. TDD RED/GREEN 结果

### RED（对迁移前真实源码的验证，非推测）

新增测试 [test-phase03d-member-data-accessibility.mjs](../../admin-h5/scripts/test-phase03d-member-data-accessibility.mjs) 先通过 `git stash` 把 `CustomerList.vue` 真实还原到迁移前的版本运行：

```text
FAIL 1. First page reads a real backend total, not array.length pretending to be the count
FAIL 2. Requesting more members triggers a real second-page API call, not revealing more of an already-fetched array
FAIL 3. Changing the search keyword re-queries the backend, not a client-side filter over the first page
FAIL 4. A request failure resolves to Error, never a fabricated empty member list
FAIL 5. A confirmed real zero-result response resolves to Empty
FAIL 6. A refresh failure on an already-loaded, same-keyword list preserves the existing members
Phase-03D RED failures: 6
```

6 个用例全部 FAIL——这是本阶段四次 Touch And Migrate 里缺陷面最大的一次，符合审计结论（分页、总数、失败态三个维度都不符合）。

### GREEN

`git stash pop` 恢复迁移后的代码，重新运行：

```text
$ npm run test:phase03d-member-data-accessibility
PASS 1. First page reads a real backend total, not array.length pretending to be the count
PASS 2. Requesting more members triggers a real second-page API call, not revealing more of an already-fetched array
PASS 3. Changing the search keyword re-queries the backend, not a client-side filter over the first page
PASS 4. A request failure resolves to Error, never a fabricated empty member list
PASS 5. A confirmed real zero-result response resolves to Empty
PASS 6. A refresh failure on an already-loaded, same-keyword list preserves the existing members
Phase-03D member data accessibility: passed
```

### 回归测试

```text
$ npm run test:performance-observability → 11/11 pass（markPageContentReady 埋点字段/调用点未改动）
```

未运行 `npm run build`：本阶段改动限定在一个视图文件内部的数据获取与状态判断逻辑，不涉及依赖、类型或构建配置。仓库里没有其它测试脚本引用 `CustomerList.vue` 或 `getCustomers`（已用 grep 核实），因此没有更多需要复跑的既有测试。

## 7. 风险评估

- **会员业务模型未被改变**：`getCustomers`/`deleteCustomer`/`restoreCustomer` 的调用方式、会员的停用/恢复/发券逻辑、`isActive`/`formatPhone`/`formatMemberNo` 等展示函数均未触碰；本阶段只改变了"请求哪一页、总数从哪来、失败时清不清空数据"。
- **未修改后端**：`saas-base` 全程只读核实（`app/api/v1/customers.py`、`customer_service.py`、`app/core/pagination.py`），未做任何修改；`page_size:30` 在后端 `PAGE_MAX_LIMIT=200` 的上限内，不会被截断或拒绝。
- **"加载更多"失败的重试路径**：`loadMore()` 失败时只用 `message.error` 提示，没有像其它三个 Phase 那样加一条常驻横幅。这是刻意的最小化处理：失败不影响已经正确显示的数据，"加载更多"按钮本身还在原地可再次点击，是一个已经可见的重试入口；不像首屏失败会让整页看不到任何东西，不需要额外的持久化视觉承诺。
- **关键词不匹配这条判断的复杂度**：新增了 `loadedKeyword` 状态，用于区分"这次刷新失败但关键词没变，旧数据仍可信"和"关键词已经变了，旧数据不该被冒充成新结果"。这比单纯"失败就显示旧数据"多了几行代码，但直接服务于 Jobs 里"让老板相信会员数据"这一条——展示一个不属于当前搜索的会员列表本身就是一种状态失真，即使技术上"数据没丢"。
- **回归风险低**：改动集中在 `loadCustomers`/`loadMore` 两个函数和对应的模板分支；会员卡片本身的渲染、操作按钮、跳转路径均未改动。

## 8. 后续建议

1. **P1（不在本阶段执行）**：当前页面仍然没有等级、积分、消费价值等经营分层筛选，会员列表还是"能查到人"而不是"能理解会员价值"的经营工作台，这是 Phase-01 §2.2 记录的效率问题，需要独立的产品设计任务，不属于状态真实性范畴。
2. **P2（不在本阶段执行）**：`loadMore()` 目前每次追加 30 条，随着已加载会员越来越多，`customers.value` 数组会持续增长；如果未来有商家反馈大规模会员库下滚动或内存有问题，应该用真实设备和数据规模的测量结果决定是否需要窗口化，而不是现在凭猜测处理。
3. **P2（观察）**：`loadedKeyword` 目前只处理"关键词变化"，如果未来给这个页面加真实的等级/消费筛选，需要同步扩展这个"当前展示数据对应哪一次查询"的判断，不能只看关键词。

```text
FINAL_DECISION=RESULT A: MEMBER_DATA_ACCESSIBILITY_READY
```

## ACCEPTANCE：验收回答

1. **后台看到的会员数量是否真实？** 是。`total` 现在来自后端真实的 `COUNT(*)` 查询结果（`data.total`），不再用当次请求返回的行数（曾经被 100 条硬性截断）冒充总数。
2. **分页是否由后端驱动？** 是。`page` 参数在翻页时真实递增并发送到后端，`loadMore()` 每次都是一次新的网络请求；不存在任何"展开本地已拉取数组"的客户端伪分页。
3. **搜索是否真实查询？** 是。关键词通过 `params.search` 发送到后端，由 `saas-base` 的 `WHERE phone LIKE ... OR name LIKE ...` 真实过滤；本阶段额外确保了搜索结果同样享有真实分页（不再被固定 100 条截断），且失败时不会把上一个关键词的结果误显示为当前查询结果。
4. **接口失败是否误显示空会员？** 不会。业务失败（曾经遗漏 `loadError.value=true` 的那条分支）现在和网络失败统一走同一个 `throw/catch`，必定进入错误态；有旧数据时保留展示并加警示条，无旧数据或关键词已变时展示独立错误态，两种情况都不会落入"还没有会员"的假空态。
5. **是否符合 Phase-02 数据真实性规则？** 符合。Loading/Success/Empty/Error 四态互斥且真实；Unknown 状态在本页面没有独立场景（没有"无法确认但也不算失败"的中间态），因此没有为了凑合同齐全虚构一个；分页合同（page/pageSize/keyword 必须与后端请求一致、禁止客户端伪分页）全部落实。
