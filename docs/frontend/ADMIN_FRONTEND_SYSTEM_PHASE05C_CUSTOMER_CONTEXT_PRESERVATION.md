# CustomerList 工作上下文保持（Phase-05C）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-05C
STATUS=CUSTOMER_LIST_WORK_CONTEXT_PRESERVATION
MODE=AUDIT_FIRST_THEN_TECHNICAL_DECISION_THEN_MINIMAL_IMPLEMENTATION
PHASE_TYPE=SINGLE_PAGE_CONTEXT_CONTINUITY_OPTIMIZATION
```

## 0. Baseline

```text
BASELINE_SHA = 8f2bba8e6498815d55718ab37f4f8fa247ded052
BRANCH = main
WORKTREE_STATUS（开始时）=
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条工作线）
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 与本阶段无关，全程未删除、未 reset、未 clean、未 stash、未混入本阶段提交。Phase-05A（OrderManage）、Phase-05B（MenuManage）均已完成，本阶段未再触碰这两个文件。

## 1. CustomerList Core Job

| 项 | 内容 |
| --- | --- |
| 谁 | 餐厅老板 / 运营人员 |
| 触发 | 需要查找并查看某个会员 |
| 任务 | 输入搜索条件 → 找到目标会员 → 进入会员详情 → 查看信息 → 返回列表 → 继续刚才的会员查找/运营工作 |
| 成功标准 | 返回之后不需要重新输入已经输入过的信息、不需要重新翻已经翻过的分页、不需要重新寻找刚才的位置；同时不能展示跨租户或过期的错误上下文 |

## 2. 产品概念与真实文件 / Route 映射

```text
PRODUCT_CONCEPT = MemberManage / 会员管理
REAL_LIST_FILE = admin-h5/src/views/CustomerList.vue（当前 HEAD 270 行，本阶段结束后 335 行）
REAL_DETAIL_FILE = admin-h5/src/views/CustomerDetail.vue（367 行，本阶段未修改）
LIST_ROUTE = /customers（router/index.js:79，name: CustomerList）
DETAIL_ROUTE = /customers/:id（router/index.js:80，name: CustomerDetail）
MAPPING_VERIFIED = YES
```

已在当前 HEAD 用 `grep`/直接阅读核实：两个路由是 `Layout` 下的同级子路由，都没有 `meta.keepAlive`；`CustomerDetail.vue` 用 `<PageHeader title="会员详情">` 承载返回入口（`PageHeader.vue` 内部固定 `@click="router.back()"`）。没有凭历史报告直接假定文件名。

## 3. 当前 Context Loss 真实路径（PART_01）

```text
LIST_ROUTE = /customers
DETAIL_ROUTE = /customers/:id
NAVIGATION_METHOD = router.push（CustomerList.vue:goToDetail，迁移前 router.push(`/customers/${id}`)）
BACK_METHOD = PageHeader.vue 内置的 router.back()（CustomerDetail.vue 复用 PageHeader，未自定义返回逻辑）
LIST_COMPONENT_UNMOUNTED = YES
LIST_STATE_DESTROYED = YES
KEEP_ALIVE_CURRENT = NO
```

已用 `grep -rn "keep-alive|KeepAlive|keepAlive"` 核实全仓库 `admin-h5/src` 没有任何 keep-alive 用法；`composables/useOrderAlert.js:5` 里甚至有一行现成注释直接证实这是刻意的架构选择："后台的 Tab 切换是 `<router-view>` 不带 keep-alive，每次从…"。`Layout.vue:3` 的 `<router-view v-slot="{ Component }">` 没有包 `<keep-alive>`。因此：进入详情、返回列表，`CustomerList.vue` 组件实例被完整销毁再重新创建，`keyword`/`page`/`customers` 等所有 `ref` 全部丢失，`onMounted` 重新以空关键词、第 1 页发起请求——这就是 Phase-05 报告记录的 Context Loss，本阶段用真实代码重新证实，不是直接采信旧结论。

## 4. 当前页面状态资产（PART_02）

| 状态 | 变量名 | 来源 | 是否服务器驱动 |
| --- | --- | --- | --- |
| SEARCH_KEYWORD | `keyword`（ref） | 用户输入，随 `params.search` 发给后端 | 是（Phase-03D 已验证的真实后端搜索） |
| PAGE | `page`（ref） | 已加载到第几页（累计"加载更多"的深度） | 是（`getCustomers({page, page_size})`） |
| PAGE_SIZE | `PAGE_SIZE`（模块级 `const`，固定 30） | 硬编码，当前用户不可修改 | — |
| TOTAL | `total`（ref） | 后端返回的真实总数 | 是 |
| FILTERS | 不存在 | — | — |
| SORT | 不存在 | — | — |
| LOADING | `loading`/`loadingMore`（ref） | 前端本地状态 | — |
| ERROR | `loadError`（ref） | 前端本地状态 | — |
| CURRENT_ROWS | `customers`（ref 数组） | 后端返回，映射后存放 | 是 |
| SCROLL_STATE | 不存在显式管理 | — | — |

Phase-03D 已经把 `keyword`/`page`/`total` 修成真实后端驱动，本阶段的任何方案都不允许倒退回"恢复一份过期数组后不再请求"的状态——第 6/9/11 节的最终方案会反复回到这条约束。

## 5. 隐私与多租户约束（PART_04/PART_09/PART_10）

```text
CAN_KEYWORD_CONTAIN_PHONE = YES（搜索框占位符原文就是"搜手机号或姓名"）
CAN_KEYWORD_CONTAIN_PII = YES（手机号、姓名均为会员 PII）
ROUTE_QUERY_PRIVACY_RISK = HIGH（若把 keyword 放进 URL）
```

按 PART_04 的规则，`keyword` 一旦可能包含手机号，默认禁止用 `?keyword=138xxxxxxxx` 这种 Route Query 方案——URL 会进入浏览器历史、可能被服务端访问日志记录、可能出现在 Referer、可能被截图/录屏捕获。本阶段的技术方案（第 6/7 节）从一开始就排除了"把 keyword 放进 URL"这个选项，不是事后弥补。

```text
CONTEXT_KEY = 是（identity = tenant_id + token 拼接，见第 9 节）
TENANT_SWITCH_CLEAR = YES（identity 不匹配即拒绝恢复，见测试 5）
LOGOUT_CLEAR = YES（token 变化即 identity 不匹配，见测试 6）
SESSION_CHANGE_CLEAR = YES（同上机制覆盖）
PERMISSION_CHANGE_BEHAVIOR = 不适用——本方案不缓存权限相关数据，只缓存 keyword/page，权限变化本身不影响这两个字段的正确性；真正的权限校验仍然由路由 `meta.requiresPermission` 和后端接口各自把关，本阶段未改动
```

## 6. 技术方案评估（PART_05）

### OPTION A — Route Query

```text
IMPLEMENTATION_COST = 低（只需要 router.push 带 query）
REFRESH_RECOVERY = 是（URL 天然刷新后还在）
BACK_FORWARD_BEHAVIOR = 天然支持浏览器前进/后退
PRIVACY_RISK = 高（如果把 keyword 放进去）——若只放 page，隐私风险低，但无法覆盖 keyword 这个最重要的字段
TENANT_SAFETY = 中——URL 本身不含租户信息，如果 URL 被复制到另一个租户会话打开，page 参数会被套用到错误的租户查询上（虽然查询本身仍然是那个新会话的真实请求，不会串数据，但语义上容易造成"这个 URL 对应的是谁的会员列表"的混淆）
ROUTER_COMPLEXITY = 低
CURRENT_ARCHITECTURE_MATCH = 高（Router 已经在用，不需要新依赖）
```

**结论**：Option A 单独无法覆盖 `keyword`（隐私风险不可接受），只能覆盖 `page`。而 `keyword` 恰恰是 CORE_JOB 里最需要保留的字段——老板搜"张三"进详情再回来，如果关键词没了，等于任务基本没完成。Option A **不能单独作为完整方案**。

### OPTION B — Scoped Page State（sessionStorage，键值极小）

```text
NEW_STATE_OWNER_REQUIRED = 是，但极小——一个 sessionStorage key，值只有 {identity, keyword, page} 三个字段，不新建 store/composable 文件
LIFECYCLE_CLEAR_RULE = 消费型读取：onMounted 读到即删除；正常进入（非回程）永远读不到
TENANT_KEYING = identity = tenant_id + token 拼接（跟 useWorkbenchSync.js 的 currentIdentity() 同一种做法），读取时必须完全匹配当前身份
LOGOUT_CLEAR = 退出登录后重新登录会拿到新 token，identity 必然不同，旧上下文永远读不出来（细节见第 10 节）
REFRESH_BEHAVIOR = sessionStorage 在同一个标签页里刷新后依然存在——但因为是"消费型读取"，只有真的从详情页返回这条路径会写入，普通刷新 `/customers` 本身不会经过 goToDetail，不会产生一条可供刷新后"意外恢复"的记录
IMPLEMENTATION_COST = 低——全部改动在 CustomerList.vue 一个文件内
REGRESSION_RISK = 低——不改变 loadCustomers 的默认调用行为，只新增可选参数
```

### OPTION C — Selective KeepAlive（仅评估，未采用）

```text
CAN_SCOPE_TO_CUSTOMER_LIST = 技术上可以（Vue 3 `<keep-alive include="CustomerList">`），但要求组件必须有可匹配的 name——当前所有 `<script setup>` 页面都没有显式 `defineOptions({ name })`，需要先补
COMPONENT_INSTANCE_PRESERVED = YES（这正是 keep-alive 的目的）
NETWORK_STATE_PRESERVED = YES，但这恰恰是问题所在——详情页可能已经修改了会员状态（第 13 节），保留旧的网络请求结果意味着要额外写激活时重新拉取的逻辑，等于还是要走一次真实请求，keep-alive 本身省下的"重新请求"这一步反而必须主动放弃
SCROLL_PRESERVED = YES（DOM 不销毁，天然保留，是 C 相对 A/B 唯一的真实优势）
ACTIVATED_NEEDED = YES（需要在 activated 钩子里重新发起真实请求，因为不能假设旧数据仍然新鲜）
DEACTIVATED_NEEDED = 可选
TENANT_SWITCH_RISK = 中——keep-alive 缓存的组件实例在租户切换时不会自动感知，需要额外在 activated 或全局守卫里做身份校验，等于重新实现 Option B 已经在做的 identity 校验，但复杂度更高
STALE_DATA_RISK = 中——DOM 和内存都保留，如果开发者以后不小心在 activated 里漏掉重新请求，就会真的展示过期数据，风险比 A/B 高（A/B 从架构上就不可能展示旧数据，因为组件每次都是全新创建）
IMPLEMENTATION_COST = 中高——需要给目标组件加 name、改 Layout.vue 的 router-view 结构（全局共享文件）、处理 activated/deactivated 生命周期
REGRESSION_RISK = 中高——Layout.vue 是所有页面共用的渲染出口，改动方式无论多么"scoped"，改的都是这一个全局文件，且这是本仓库第一次引入 keep-alive，没有先例可循
```

**ARCHITECTURE_CHANGE_GATE 判定**：Option C 需要修改 `Layout.vue`（全局 `router-view`），触发 PART_17 的 `ARCHITECTURE_SCOPE_EXPANSION_REQUIRED=YES`。按规则必须先确认是否存在更小方案——Option A/B 都完全不需要碰 `Layout.vue`/router 全局结构，证明存在安全的局部方案。因此 **Option C 不进入最终 A/B 比较**，只停留在纸面评估，不实现。这也符合 STRICT_RULES 第 10 条"不给整个 admin-h5 加全局 keep-alive"和 PART_18"global keep-alive 禁止"的精神——即使是 scoped include，启用机制本身仍是全局的。

## 7. A/B 正反方评审（PART_07）

```text
SOLUTION_A = Route Query（仅 page，不含 keyword）
SOLUTION_B = Scoped sessionStorage 状态（keyword + page，identity 校验，消费型读取）
```

| 维度 | SOLUTION_A | SOLUTION_B |
| --- | --- | --- |
| JOB_MATCH | 部分——只能恢复 page，恢复不了 keyword，Job 没有真正完成 | 完整——keyword + page 都能恢复 |
| STATE_MINIMALITY | 高（只有一个 query 参数） | 高（一个 sessionStorage key，三个字段） |
| PRIVACY | keyword 被排除在外，安全，但代价是功能不完整 | keyword 走 sessionStorage，不进 URL/历史/日志/Referer/截图，风险可控 |
| TENANT_ISOLATION | 弱——URL 本身不携带身份信息，无法在读取时校验"这个 page 参数是不是当前租户查出来的" | 强——identity 校验是读取的前置条件 |
| REFRESH_BEHAVIOR | 天然支持 | 消费型读取下不需要，也不适用（见第 6 节） |
| BACK_NAVIGATION | 天然支持浏览器前进/后退 | 依赖组件 `onMounted` 触发，浏览器前进/后退一样会触发（页面仍会整个重新挂载） |
| STALE_DATA_RISK | 低（每次都是真实请求） | 低（每次都是真实请求，见第 11 节 RELOAD_CURRENT_QUERY） |
| IMPLEMENTATION_COST | 低 | 低 |
| MAINTENANCE_COST | 低，但因为覆盖不了 keyword，后续大概率需要再补一个机制去处理 keyword，等于多维护两套 | 低，一套机制覆盖两个字段 |
| REGRESSION_RISK | 低 | 低 |

```text
POSITIVE_CASE_A = 天然支持浏览器前进/后退和刷新；实现极简单
NEGATIVE_CASE_A = 无法覆盖 keyword（隐私红线），单独使用无法满足 CORE_JOB；如果为了覆盖 keyword 再叠加一个机制，就变成事实上的 Hybrid，复杂度不降反升
POSITIVE_CASE_B = 一套机制同时覆盖 keyword 和 page；identity 校验天然解决租户隔离和登出失效；不产生任何隐私暴露面
NEGATIVE_CASE_B = 不支持"复制 URL 分享具体页码"这种场景——但 CORE_JOB 里没有这个真实需求，不是本阶段要解决的问题
```

```text
RECOMMENDATION = SOLUTION_B
```

理由：Solution A 单独就无法完成 Job（keyword 是隐私红线，不能上 URL），必须叠加别的机制才勉强够用，这本身已经违反"只能有一个权威"（PART_08）；Solution B 用一套机制、一个状态权威，同时满足隐私、租户隔离、Job 完整性三个约束，且不需要触碰任何全局文件。不采用 PART_06 的 Hybrid（Option D）：混合方案只有在"明显降低复杂度/风险"时才允许，而这里 Solution B 单独已经能完整解决问题，叠加 Route Query 只会增加状态权威的数量，违反 PART_08，没有必要。

## 8. Final Technical Decision

采用 Solution B：sessionStorage 保存 `{identity, keyword, page}`，消费型读取（读到即删）。这是当前证据支持的最小、最安全方案——不改后端、不改数据库、不改 `Layout.vue`/router 全局结构、不引入新依赖，风险面严格限定在 `CustomerList.vue` 一个文件内。

## 9. State Ownership Contract

```text
CONTEXT_STATE_OWNER = sessionStorage 的单个 key（admin_customer_list_context），只由 CustomerList.vue 读写
```

没有 route query、没有 Pinia store、没有 localStorage、没有跨组件共享的 ref 同时存在——`saveListContext()`（写）和 `consumeSavedListContext()`（读+删）是这份状态唯一的两个入口，都在同一个文件里，不存在"四份互相同步"的风险（PART_08 明确禁止）。`CustomerDetail.vue` 完全不知道这份状态的存在，也不需要知道——它只是被 `router.push`/`router.back()` 正常导航到/离开，本阶段未修改这个文件。

## 10. Tenant / Logout Lifecycle

```text
CONTEXT_KEY = 包含 tenant identity（tenant_id + token 拼接）
TENANT_SWITCH_CLEAR = YES
LOGOUT_CLEAR = YES
SESSION_CHANGE_CLEAR = YES
```

已用真实代码路径核实（`stores/auth.js`/`utils/session.js`）：`More.vue:127-132` 的 `logout()` 调用 `auth.logoutCurrentDevice()`/`auth.clearAuth()` 后 `router.push('/login')`——是 SPA 内部导航，不是整页刷新，这意味着任何"模块级 JS 变量"式的方案都会在 logout 后继续存活于内存中，必须显式处理；本方案没有走"模块级变量"，而是每次读取都用 `currentContextIdentity()`（`tenant_id`+`token` 现读 `localStorage`）跟保存时的 identity 比较，`clearAuth()`（`stores/auth.js`）会清掉 `token`（`clearSession()`），重新登录会写入新 token（`utils/session.js:19` `saveSession`），identity 字符串必然改变——第 10/8 节的测试用真实的 identity 拼接逻辑验证了这一点，不是假设。

## 11. Return Data Freshness Contract

```text
RETURN_FETCH_POLICY = RELOAD_CURRENT_QUERY
```

不是"REUSE_THEN_REVALIDATE"（先展示旧数据再后台核实）——本方案根本不保存 `customers` 数组本身，只保存 `keyword`/`page` 这两个查询参数；返回后永远发起一次新的、真实的 `getCustomers()` 请求。这直接满足 PART_12 的 STALE_DATA_CONTRACT（"我们要保存的是'老板刚才在找什么'，不是永久保存'老板刚才看到的会员数据'"），也让第 13 节的 DETAIL_MUTATION_EFFECT 天然无需特殊处理。

## 12. Touch And Migrate

**实际修改文件**：`admin-h5/src/views/CustomerList.vue`（业务代码）+ `admin-h5/scripts/test-phase05c-customer-context-preservation.mjs`（新增测试）+ `admin-h5/scripts/test-phase03d-member-data-accessibility.mjs`（更新，见下方说明）+ `admin-h5/package.json`（仅注册测试命令）。未修改 `CustomerDetail.vue`、`router/index.js`、`Layout.vue`、任何 store、任何 API、数据库。

### Before → After

```js
// Before
async function loadCustomers() {
  loading.value = true
  page.value = 1
  ...
  const params = { page: 1, page_size: PAGE_SIZE }
  ...
}
function goToDetail(id) { router.push(`/customers/${id}`) }
onMounted(loadCustomers)

// After
async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {
  loading.value = true
  page.value = 1
  ...
  const params = { page: 1, page_size: restorePageSize }
  ...
  page.value = restorePage   // 成功后才真正生效
  ...
}
async function restoreListContext(saved) {
  keyword.value = saved.keyword || ''
  const cappedPage = Math.max(1, Math.min(Number(saved.page) || 1, Math.floor(RESTORE_PAGE_SIZE_CAP / PAGE_SIZE)))
  await loadCustomers({ restorePage: cappedPage, restorePageSize: cappedPage * PAGE_SIZE })
}
function goToDetail(id) {
  saveListContext()
  router.push(`/customers/${id}`)
}
onMounted(() => {
  const saved = consumeSavedListContext()
  if (saved) restoreListContext(saved)
  else loadCustomers()
})
```

`loadCustomers()` 默认参数（`restorePage=1, restorePageSize=PAGE_SIZE`）跟原来无参调用时的硬编码值完全一致，首次加载/手动刷新/换关键词搜索/停用恢复后的重新加载这些既有调用点**一个字符都没改**，行为不变。

**恢复深度的实现**：不是连续发起 N 次"加载更多"，而是用一次更大的 `page_size`（`cappedPage * PAGE_SIZE`，封顶 `RESTORE_PAGE_SIZE_CAP=200`，对应 saas-base `PAGE_MAX_LIMIT`）在"第 1 页"请求里一次性拿回相当于原来 N 页的真实数据，请求完成后把内部 `page` 计数设置为 `cappedPage`，让后续"加载更多"从正确的深度继续。超出 200 条上限时只能恢复到上限允许的最大整页数，不是失败，也不是伪造数据——只是老实地说"恢复不了那么深，从这里继续翻"。

**已知的一处简化，写进 Deferred Issues（第 18 节）**：如果"恢复"这次请求本身失败（网络问题），`page.value` 会停在 1（`loadCustomers` 开头就重置），错误态的"重试"按钮会重新以 `keyword` 为条件的第 1 页重新加载，不会自动重试恢复到原来的深度——这是一个可接受的降级，不是数据错误，只是恢复深度这个次要目标在失败重试路径上没有被特别保留。

### 为什么必须同时更新 Phase-03D 的既有测试

`loadCustomers()` 的函数签名从 `async function loadCustomers() {` 变成 `async function loadCustomers({ restorePage = 1, restorePageSize = PAGE_SIZE } = {}) {`——这是本阶段的合法、刻意改动。`test-phase03d-member-data-accessibility.mjs` 有 5 处用精确字符串 `'async function loadCustomers() {'` 切片函数体，签名一变这些切片全部失效（`marker not found`）。这不是这些测试断言的行为真的被破坏了，是它们定位函数体的字符串标记过期了——已经把 5 处标记同步更新为新签名，切片终点也从 `'\n// 翻页'`（会把新增的 `restoreListContext` 一起切进来）收紧为 `'\n\n// 从详情返回时调用'`，让切片精确停在 `loadCustomers` 结束处，不多不少。更新后 Phase-03D 的 6 个用例全部保持 PASS（第 14 节）。

## 13. Detail Mutation Effect（PART_13）

```text
DETAIL_CAN_MUTATE_LIST_FIELDS = YES
RETURN_DATA_REFRESH_REQUIRED = YES
```

已核实 `CustomerDetail.vue:269-291` 的 `disableCustomer()`/`restore()` 会调用 `updateCustomerStatus(...)` 真实修改会员的 `status` 字段——这正是 `CustomerList.vue` 列表行里"正常/已停用" `a-tag` 展示的字段。因为第 11 节确定的策略是 `RELOAD_CURRENT_QUERY`（返回后永远重新真实请求），这类修改天然会在返回列表时被看到，不需要任何额外代码：本方案从设计上就不可能展示"详情页改完，列表还是旧值"这种情况。

## 14. TDD RED → GREEN

新增 [test-phase05c-customer-context-preservation.mjs](../../admin-h5/scripts/test-phase05c-customer-context-preservation.mjs)，覆盖 PART_15 要求的全部 9 项（TEST 0 是行为镜像与真实实现一致性的前置校验；TEST 3 按真实代码核实 CustomerList 当前没有 filter，记录 `NOT_APPLICABLE`）。

### RED（对迁移前真实源码验证，方法：`git show BASELINE_SHA:...` 输出到临时文件后跑同等断言，未使用 stash，未触碰工作区任何文件，验证完成后临时文件已删除）

```text
FAIL 0. currentContextIdentity/saveListContext exist
FAIL 4. restoreListContext exists and calls loadCustomers
FAIL 9. onMounted checks for a saved context before loading
RED-check failures (expected on baseline): 3
```

（TEST 1/2/5/6 是纯行为镜像测试，用固定 JS 逻辑对着一份内存里的假 `sessionStorage`/`localStorage` 验证，不依赖源码字符串，因此在旧代码上"技术上也会通过"——它们验证的是"如果按这个逻辑实现，行为是否正确"，真正证明"旧代码里这个逻辑不存在"的是 TEST 0/4/9 这三个源码结构断言，三者在旧代码上如实 RED。）

### GREEN

```text
$ npm run test:phase05c-customer-context-preservation
PASS 0. The mirror above matches the real save/consume/identity logic verbatim
PASS 1. A keyword typed before opening a detail is restored on return
PASS 2. A page depth beyond 1 is restored on return
PASS 3. No real filter exists on CustomerList -- NOT_APPLICABLE, confirmed by source inspection
PASS 4. Restoring never reuses a stale in-memory array -- it always re-requests the real backend
PASS 5. Tenant A's saved context can never be restored under Tenant B's identity
PASS 6. A logout (token rotation) invalidates any saved context, even for the same tenant
PASS 7. A failure after returning from detail still follows the Phase-03D Error contract, not a fake success
PASS 8. Returning after a detail-side status change always re-fetches -- restore is never a frozen snapshot
PASS 9. A normal first-time entry (no prior detail visit) starts with an empty, non-inherited context
PASS No global keep-alive, no route query for keyword, no new large state dependency
Phase-05C customer context preservation: passed
```

`NO_PRODUCT_RED` 不适用——本阶段的核心能力（跨详情页往返保持上下文）在迁移前完全不存在，不是"已经合规不需要造假 RED"的情况。

### 测试质量说明（PART_16）

没有只测试源码里有没有 `sessionStorage`/`route.query` 这类字符串。TEST 1/2/5/6/9 用真实的 Map 实现了一个假的 `sessionStorage`/`localStorage`，把源码里 `saveListContext`/`consumeSavedListContext`/`currentContextIdentity` 的真实逻辑原样搬过来跑（TEST 0 锁定这份镜像和源码逐字一致），验证的是"保存 - 消费 - identity 校验"这个状态机本身的正确性，包括跨租户（TEST 5）、登出后 token 变化（TEST 6）这类真实场景，而不是"文件里出现了某个词"。局限：仓库没有 Vue Router 级别的测试框架，无法验证 `router.push`/`router.back()` 触发组件卸载重建、`onMounted` 真的会被调用这类 Vue Router 自身的行为——这部分依赖 Vue Router 3/4 本身的既有保证（第 3 节已用源码核实当前架构没有 keep-alive，卸载重建是默认行为），本阶段没有对此做超出源码级别的运行时断言。

## 15. Regression Gates

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `npm run test:phase05c-customer-context-preservation` | 11/11 PASS |
| 2 | `npm run test:phase03d-member-data-accessibility` | 6/6 PASS（发现并修复了因函数签名变化导致的测试标记失效，见第 12 节，修复后全部 PASS） |
| 3 | `node scripts/test-performance-observability.mjs` | 11/11 PASS |
| 4 | Router / Navigation 相关测试 | 不适用——仓库没有独立的 Vue Router 测试文件；本阶段唯一涉及导航的改动（`goToDetail` 内新增 `saveListContext()` 调用）已被本阶段测试第 1/2 项覆盖 |
| 5 | `npm run test:phase04-component-adoption-governance` | 6/6 PASS（与 CustomerList 无直接交集，确认未受影响） |
| 6 | `npm run check` | 全链路通过，含以上全部已注册测试 |
| 7 | `npm run build` | `✓ built in 18.26s`，无编译错误 |

```text
NEW_FAILURE = 0
```

`grep -rl "CustomerList.vue\|CustomerDetail.vue" scripts/*.mjs` 确认涉及这两个文件的全部测试（`test-performance-observability.mjs`、`test-phase03d-member-data-accessibility.mjs`、本阶段新增文件）均已在上表覆盖，没有 Phase-05A 那种"遗留在 `npm run check` 之外"的既有测试。`test-phase03d-member-data-accessibility.mjs` 的更新是本阶段合法改动导致的必要同步，不是"顺手修无关失败"。

## 16. Browser Verification

```text
BROWSER_VERIFICATION=NOT_RUN
REASON=本机没有可用于 CustomerList/CustomerDetail 的登录态或可用的开发/staging 后端（需要真实商家账号 + 真实会员数据才能观察到搜索→翻页→详情→返回的实际效果，以及租户切换场景）。`npm run build` 已确认改动可以正确编译成生产构建。自动化合同测试（第 14 节）用真实的存储读写逻辑和身份校验场景验证了状态机本身，不用浏览器验证冒充完成。
```

## 17. Before / After Efficiency

真实案例：搜索"王"，翻到第 3 页，打开王某会员详情，查看，返回，继续找会员。

### BEFORE

```text
KEYWORD_REENTRY = YES（要重新输入"王"）
PAGE_REENTRY = YES（要重新点 2 次"加载更多"才能回到第 3 页深度）
FILTER_REENTRY = N/A（当前无 filter）
REPEAT_CLICKS = 至少 2 次（重新点加载更多）
REPEAT_TYPING = 1 次完整关键词输入
CONTEXT_RECOVERY_COST = MEDIUM-HIGH
```

### AFTER

```text
KEYWORD_REENTRY = NO
PAGE_REENTRY = NO
FILTER_REENTRY = N/A
RETURN_TO_WORK_STEPS = 0（点击返回后直接就是之前的查询结果，不需要任何额外操作）
CONTEXT_RECOVERY_COST = LOW
```

不是"减少一个点击"这种模糊结论：消除的是"从头再来"这整条重复路径——尤其是当会员总数较多、老板需要连续核对多个同名/相似会员时，这个差异会被使用次数直接放大。

## 18. Scope Audit / Deferred Issues

```text
SCOPE_EXPANDED = NO
```

未修改会员后端 API、数据库、会员业务模型、会员分页合同、后端搜索合同；未重新实现前端伪分页（`RESTORE_PAGE_SIZE_CAP` 用的仍然是同一个真实 `getCustomers` 接口，只是这一次请求的 `page_size` 更大，不是本地切片）；未缓存全部会员数据到 `localStorage`（用的是 sessionStorage，且只存 3 个字段，不存会员行数据）；未把完整会员记录或敏感搜索词写入 URL；未给整个 admin-h5 加全局 keep-alive（第 6 节已论证并放弃 Option C）；未缓存所有后台页面；未建立通用页面状态框架（状态机只服务这一个文件的这一个场景）；未引入新的大型状态管理依赖（没有新增 Pinia store，没有新增第三方库）；未修改 OrderManage/MenuManage；未扩建 CRM 功能；未新增会员标签；未新增会员营销；未做性能专项。

**Deferred（仅记录，本阶段不实现）**：

1. **Scroll position 恢复**：按 PART_14 定性为 SHOULD 而非 MUST。当前列表结构是简单纵向卡片流（非虚拟滚动、非表格），`keyword`+`page` 恢复后老板已经能直接看到之前那批结果，翻到大致正确的位置成本不高；引入滚动位置缓存需要额外的 DOM 测量和恢复时机处理，复杂度收益比不划算，本阶段 `DEFER_SCROLL_PRESERVATION`。
2. **恢复请求失败时不会保留原始恢复深度**（第 12 节已说明）：失败后的重试会退回到该关键词的第 1 页，不是错误，只是次要目标在这一条失败路径上做了简化。

## 19. Phase-05 Closure

| 子阶段 | 页面 | 核心 Job | 结果 |
| --- | --- | --- | --- |
| 05A | OrderManage | 新订单发现 + 拒单安全 | `ORDER_HIGH_FREQUENCY_EFFICIENCY_READY` |
| 05B | MenuManage | 菜品快速查找 | `MENU_HIGH_FREQUENCY_EFFICIENCY_READY` |
| 05C | CustomerList | 工作上下文保持 | `CUSTOMER_CONTEXT_PRESERVATION_READY`（本报告） |

三项全部完成，声明：

```text
HIGH_FREQUENCY_TASK_EFFICIENCY_BASELINE_V1_READY
```

## ACCEPTANCE

1. **会员搜索后进入详情再返回，keyword 是否保留？** 是。第 14 节测试 1、第 17 节 Before/After。
2. **page 是否保留？** 是（在 `RESTORE_PAGE_SIZE_CAP` 允许范围内精确保留，超出范围时保留能恢复的最大整页数并如实反映，不伪造）。第 14 节测试 2。
3. **filters 是否保留？** 不适用——当前 CustomerList 没有真实存在的 filter（第 4 节已核实），测试 3 记录为 `NOT_APPLICABLE`。
4. **是否仍然使用 Phase-03D 的真实后端搜索/分页？** 是。恢复路径和普通路径共用同一个 `loadCustomers()`/`getCustomers()` 调用，第 14 节测试 4/7 已验证。
5. **是否避免保存完整会员数据作为长期真相？** 是。sessionStorage 只存 `{identity, keyword, page}`，不存 `customers` 数组，第 14 节测试 8 已验证。
6. **是否明确返回后的数据刷新策略？** 是。第 11 节：`RELOAD_CURRENT_QUERY`，每次都是真实新请求。
7. **是否避免 URL 暴露手机号等敏感搜索词？** 是。第 5/6 节已论证并排除 Route Query 承载 keyword 的方案，keyword 只经过 sessionStorage，不进入 URL/浏览器历史/服务端日志。
8. **是否防止 Tenant A 上下文出现在 Tenant B？** 是。第 9/10 节 identity 校验机制，第 14 节测试 5 用真实的双租户场景验证。
9. **是否防止 logout 后恢复旧会员上下文？** 是。第 10 节，第 14 节测试 6 用真实的 token 轮换场景验证。
10. **是否没有给整个 admin-h5 加全局 keep-alive？** 是。第 6 节已评估 Option C 并因 `ARCHITECTURE_CHANGE_GATE` 主动放弃，第 14 节的架构检查测试用真实 grep 核实 `router/index.js`/`Layout.vue` 未被触碰、无 keep-alive 字样。
11. **是否只有一个上下文状态权威？** 是。第 9 节：唯一权威是 `CustomerList.vue` 内部读写的一个 sessionStorage key。
12. **是否没有引入不必要的全局状态框架？** 是。没有新建 Pinia store、没有新建composable 文件，改动全部在 `CustomerList.vue` 一个文件内。
13. **是否完成真实 RED → GREEN 或诚实记录 NO_PRODUCT_RED？** 完成了真实 RED → GREEN（第 14 节），三个源码结构断言（TEST 0/4/9）在旧代码上确认 RED，未使用 `NO_PRODUCT_RED`（本阶段的能力是真实新增的，不存在"已经合规"的情况）。
14. **是否保持 Phase-03D 数据真实性？** 是。第 15 节 Regression Gate 2，Phase-03D 全部 6 项测试仍然 PASS（因签名变化同步更新了标记，行为断言本身未改动）。
15. **是否明显降低"详情返回后从头再来"的重复成本？** 是。第 17 节量化对比，`CONTEXT_RECOVERY_COST` 从 MEDIUM-HIGH 降到 LOW。
16. **是否没有扩大到会员 CRM/营销功能？** 是。第 18 节 Scope Audit 已逐条核对。

```text
FINAL_DECISION=RESULT A: CUSTOMER_CONTEXT_PRESERVATION_READY
CONTEXT_STATE_OWNER=CustomerList.vue 内部读写的单个 sessionStorage key（admin_customer_list_context），值为 {identity, keyword, page}
KEYWORD_PRESERVED=YES
PAGE_PRESERVED=YES
FILTERS_PRESERVED=NOT_APPLICABLE
BACKEND_PAGINATION=PRESERVED
BACKEND_SEARCH=PRESERVED
TENANT_ISOLATION=PASS
PII_IN_URL=NO
GLOBAL_KEEP_ALIVE_ADDED=NO
BUSINESS_API_CHANGED=NO
DATABASE_CHANGED=NO
SCOPE_EXPANDED=NO
```

## COMMIT_RULE

```text
CHANGED_FILES=
  admin-h5/package.json
  admin-h5/src/views/CustomerList.vue
  admin-h5/scripts/test-phase03d-member-data-accessibility.mjs（更新：函数签名变化导致的标记同步，非行为变化）
  admin-h5/scripts/test-phase05c-customer-context-preservation.mjs（新增）
  docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE05C_CUSTOMER_CONTEXT_PRESERVATION.md（新增，本文件）
  PROJECT_INDEX.md
  PROJECT_KNOWLEDGE_MAP.md
STAGED_FILES=同上，仅这 7 个文件
UNRELATED_WIP_INCLUDED=NO
```

## NEXT_PHASE

Phase-05（05A/05B/05C）到此全部完成，`HIGH_FREQUENCY_TASK_EFFICIENCY_BASELINE_V1_READY`。按 REMEMBER 的指引，不继续无限优化这三个高频页面，也不擅自进入"Phase-06 组件重构"。下一步应回到 Admin Frontend System 总路线，依据 Phase-01/Phase-02 尚未完成的治理目标（信息层级、响应式、视觉系统，或其它真实证据支持的高价值问题）重新审计，再决定下一阶段主题——本报告不预先做这个判断。
