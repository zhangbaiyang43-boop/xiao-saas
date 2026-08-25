# MenuManage 高频效率 Touch And Migrate（Phase-05B）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-05B
STATUS=MENU_MANAGE_HIGH_FREQUENCY_EFFICIENCY
MODE=AUDIT_FIRST_THEN_MINIMAL_IMPLEMENTATION
PHASE_TYPE=SINGLE_PAGE_HIGH_FREQUENCY_JOB_OPTIMIZATION
```

## 0. Baseline

```text
BASELINE_SHA = 71e05c87688ff8c40a5bee251a321a9f91ec7735
BRANCH = main
WORKTREE_STATUS（开始时）=
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条工作线）
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 与本阶段无关，全程未删除、未 reset、未 clean、未 stash、未混入本阶段提交。Phase-05A 已完成（`ORDER_HIGH_FREQUENCY_EFFICIENCY_READY`），本阶段未再触碰 `OrderManage.vue`。

## 1. MenuManage Core Job

| 项 | 内容 |
| --- | --- |
| 谁 | 餐厅老板 / 店员 |
| 触发 | 需要修改某一道现有菜品 |
| 任务 | 快速找到目标菜 → 确认是正确菜品 → 完成需要的修改 → 确认修改成功 → 继续处理下一道菜 |
| 成功标准 | 不需要大量滚动查找；不需要重复无价值导航；不因效率优化破坏数据真实性；不会误操作危险动作 |

## 2. 产品概念与真实文件映射

```text
PRODUCT_CONCEPT = DishManage / 菜品管理
REAL_FILE = admin-h5/src/views/MenuManage.vue（当前 HEAD 1576 行，本阶段结束后 1591 行）
MAPPING_VERIFIED = YES
```

已用 `wc -l`/`grep` 在当前 HEAD 重新核实文件存在且内容与 Phase-03C 报告描述的结构一致（三段状态合同 `loadError`/`loadingMenu`/`allDishes` 仍在，`toggleSoldOut`/`openEdit`/`confirmDeleteDish` 等函数仍在），不是仅凭历史报告直接假定。

## 3. 当前菜品查找真实路径（PART_01）

### FLOW A — 找到某一道菜

```text
TRIGGER = 需要修改一道已知名称的菜
ENTRY = 菜单管理页
STEP_1 = 扫描分类标签栏，判断目标菜可能在哪个分类
STEP_2 = 点击该分类（或留在"全部"）
STEP_3 = 在渲染出的菜品行里肉眼扫描/滚动，找到目标菜
CLICK_COUNT = 0-1（点分类可选）+ 未知次数滚动
SCROLL_COST = MEDIUM-HIGH（取决于该分类/全部菜品数量，无搜索、无虚拟滚动、无分页，全部一次性渲染）
SEARCH_COST = HIGH（没有名称查找能力，只能靠分类+滚动这种间接方式）
NAVIGATION_COUNT = 0
DECISION_COUNT = 至少 1 次（判断分类）+ N 次（扫描每一行判断是不是目标菜）
ERROR_RISK = LOW（找错只是看错，不会误操作）
FRICTION = 菜品数量增加后，分类筛选降低的只是"要扫描的范围"，不能直接定位到目标菜；分类记忆不准确时（比如菜品分类和老板直觉不一致）反而要多试几个分类
```

### FLOW B — 修改这道菜的一个常见属性（以售罄/上下架为例，已经是最快路径）

```text
TRIGGER = 已经找到目标菜
ENTRY = 菜品行右侧的"售罄"按钮
STEP_1 = 点击"售罄"/"恢复供应"
CLICK_COUNT = 1
NAVIGATION_COUNT = 0
CONFIRMATION = 无（这是有意的高频动作，见第 8 节）
FRICTION = 无——这条路径已经是 Phase-05 审计确认过的"已经高效"范例
```

### FLOW C — 继续修改下一道菜

```text
TRIGGER = 上一道菜的修改已完成
CURRENT = 编辑抽屉是覆盖层（a-drawer），不是路由跳转，关闭后列表滚动位置和分类筛选不会重置
FRICTION = 结构上没有"重新加载丢失位置"的问题；真正的摩擦仍然是 FLOW A——处理完一道菜后，找下一道菜要重新经历同样的分类+滚动过程
```

**结论：FLOW A（查找）是三条链路里唯一的真实高摩擦点，FLOW B/C 本身结构合理。** 这与 Phase-05 冻结的 F1 结论一致，本阶段不直接采信历史结论，而是用上面的真实路径审计重新证明了它。

## 4. 主列表搜索能力核实（PART_02）

```text
MAIN_MENU_SEARCH = NO
LIBRARY_SEARCH = YES
SEARCH_SCOPE_CONFIRMED = YES
```

已在当前 HEAD 逐行核对 `MenuManage.vue` 模板：菜品主列表（第 85-157 行区域，`v-for="cat in filteredCategories"` → `dishesByCategory(cat)`）没有任何 `a-input`/`keyword`/`filter` 相关的搜索控件。唯一的搜索输入框在"菜品库导入"抽屉内（`libraryKeyword`，绑定 `doLibrarySearch`），搜索目标是**其它商户分享的菜品库**（`searchDishLibrary` API），跟当前门店已有菜品是两个完全不同的数据源——Phase-03C 处理的是这个菜品库搜索的状态真实性，不代表主列表已经有搜索能力，这一点已经用真实代码核实，不是重复历史报告的结论。

## 5. 数据来源与搜索合同（PART_03）

```text
DATA_SOURCE = allDishes（loadMenu() 调用 getMenuItems()，无任何 page/page_size/limit 参数）
CURRENT_DATA_VOLUME = 后端一次性返回完整门店菜单
BACKEND_PAGINATION = NO
BACKEND_SEARCH = NOT_NEEDED_FOR_CURRENT_SCOPE
CURRENT_LOCAL_DATA_COMPLETE = YES
```

只读核实了 `saas-base/app/api/v1/menu.py` 的 `GET /menu/items` 路由（`list_menu_items`/`_list_menu_items`）：查询语句 `select(MenuItem).where(MenuItem.tenant_id == tenant_id)` 后只加了排序（`order_by`），**没有 `.limit()`/`.offset()`**，`items = result.scalars().all()` 取出全部匹配行，响应体 `{"items": [...], "version": ...}` 里也没有 `total`/`has_more`/`next_cursor` 这类分页元信息——因为压根没有分页。对照的是同文件里另一个不同路由 `GET /dish-library`（菜品库，`.limit(200)`），二者是两个独立端点，限制不会串到 `/menu/items` 上。

```text
SEARCH_ARCHITECTURE_DECISION = 方案 A：对已完整加载到前端的 allDishes 做本地名称搜索
```

因为 `allDishes` 本来就是后端一次性给出的完整门店菜单，本地搜索不会产生"搜不到实际存在的菜品"这种数据可达性谎言——不满足 PART_03 里"只加载部分数据时禁止假搜索"的触发条件，因此不需要 RESULT B，也不需要新建后端搜索能力。

## 6. 分类 + 搜索 A/B 方案（PART_05）

| | OPTION A：搜索作用于当前分类 | OPTION B：搜索作用于全部菜品 |
| --- | --- | --- |
| DISCOVERY_COST | 较高——老板要先确认/记得自己停留在哪个分类 | 低——搜索始终意味着"搜索我的全部菜品" |
| PREDICTABILITY | 低——同样的关键词，结果随隐藏的分类状态变化 | 高——一个心智模型，不随分类 tab 变化 |
| NO_RESULT_RISK | **高**——菜确实存在，只是不在当前分类，会被误判成"不存在" | 低——只要真实存在就能找到 |
| IMPLEMENTATION_COST | 低 | 低（与 A 相近） |
| REGRESSION_RISK | 低 | 低 |

**RECOMMENDATION = OPTION B。** 依据 PART_05 的核心原则："老板输入明确菜名时，不应该因为忘记自己正停留在某个分类，导致'系统说没有这道菜'"——这正是本阶段最需要避免的一种新的、由效率优化本身引入的数据可达性谎言，跟 Phase-03C 建立的真实性合同是同一种风险，只是换了个触发场景。已用真实行为测试验证（第 10 节测试 6）。

## 7. F1 最终方案

### Before → After

```js
// Before
const filteredCategories = computed(() => activeCategory.value ? [activeCategory.value] : categories.value)
function dishesByCategory(cat) { return allDishes.value.filter(d => d.category === cat) }

// After
const filteredCategories = computed(() => {
  const q = searchKeyword.value.trim().toLowerCase()
  if (q) return categories.value.filter(cat => dishesByCategory(cat).length > 0)
  return activeCategory.value ? [activeCategory.value] : categories.value
})
function dishesByCategory(cat) {
  const base = allDishes.value.filter(d => d.category === cat)
  const q = searchKeyword.value.trim().toLowerCase()
  return q ? base.filter(d => (d.name || '').toLowerCase().includes(q)) : base
}
```

搜索状态（`searchKeyword`）是纯页面展示状态，遵循 PART_04 推荐的 `allDishes → 现有分类条件 + keyword → displayedDishes` 形态：没有复制 `allDishes`，没有建立第二份菜品数据，搜索结果继续是 `allDishes` 里的同一批真实对象引用，编辑/售罄/删除等动作对它们的操作和不搜索时完全一样。

模板新增搜索框（PART_06 位置核实：紧贴分类筛选和菜品列表之上，不在 PageHeader/页头按钮区，也不在菜品库/营销区域）：

```html
<div v-if="allDishes.length > 0" class="section-block animate-in" style="padding:0 16px 8px">
  <a-input-search v-model:value="searchKeyword" placeholder="搜菜名" allow-clear />
</div>
```

复用 Ant Design Vue 的 `a-input-search`（PART_14 要求），未引入 Vant，未扩大 Vant 使用范围，未新建组件。

**空态合同（PART_07）三态语义区分**（已用测试锁定，见第 10 节）：

- 真实没有菜：沿用既有"还没有菜品，点右上角「加菜品」开始上架"（未改动）。
- 有菜但搜索不到：新增"没有找到匹配"{{关键词}}"的菜品"，不引导去新建菜品。
- 接口失败：沿用 Phase-03C 已建立的 `loadError` 独立错误态，且求值顺序在新的搜索无结果分支之前，失败不会被重新解释成"搜索无结果"。

**分类头部批量操作的连带处理**：`toggleCategory(cat)`（"全部上架/全部下架"）内部调用的正是 `dishesByCategory(cat)`——如果搜索时不做任何处理，这个按钮点击后实际只会操作"当前分类里匹配关键词的那几道菜"，跟按钮文案暗示的"这个分类的全部菜品"会对不上。处理方式：搜索时隐藏这个按钮（`v-if="!searchKeyword.trim()"`），不改变它在未搜索时的行为语义，避免引入一个新的、容易误解的批量操作歧义。

## 8. F2 高频小修改审计（PART_09/PART_10）

| ACTION | CURRENT_FLOW | CLICK_COUNT | CONFIRMATION | FREQUENCY | ERROR_RISK | VALUE_SCORE | IMPLEMENTATION_COST | DECISION |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 上下架/售罄 | 行内按钮直接切换 | 1 | 无 | 高 | 低 | — | — | **ALREADY_EFFICIENT** |
| 价格 | 开编辑抽屉→改字段→保存 | 2 | 无 | 证据不足以判定为"高频"（见下） | 中（直接影响顾客可见价格） | 12（Phase-05 已给出） | 中 | **DEFER** |
| 分类 | 同价格，编辑抽屉内下拉框 | 2 | 无 | 同上 | 低 | — | — | **DEFER** |
| 名称/图片 | 同价格，编辑抽屉 | 2-3 | 无 | 低于价格/上下架 | 低-中 | — | — | **NOT_APPLICABLE**（本阶段未审计出比价格更值得处理的证据） |

### INLINE_ACTION_GATE 评估（针对最接近达标的候选：价格内联编辑）

```text
FREQUENCY_HIGH=?           仓库没有真实使用埋点/日志能证明价格修改比"售罄/上下架"更高频，
                            Phase-05 审计给出的 FREQUENCY_SCORE 是 3（DAILY_MEDIUM），
                            不是"高频"档，缺乏证据支撑 YES
BUSINESS_SEMANTICS_SIMPLE=YES
VALIDATION_SIMPLE=YES（必填、数字、非负，当前编辑表单已有等价校验）
ERROR_RISK_ACCEPTABLE=?    价格直接影响顾客当次下单看到的金额，行内输入误触/误存的
                            代价不低，且没有现成的"保存前二次确认"路径可以复用，
                            证据不足以判定 YES
API_ALREADY_SUPPORTS=YES（updateMenuItem 已支持部分字段更新）
STATE_RECONCILIATION_CLEAR=YES（可以沿用 saveDish 现有的成功/失败反馈模式）
MAINTENANCE_COST_DOWN=?    行内编辑需要新增独立的输入态/保存态/取消态 UI，
                            不确定比"打开已有抽屉"净减少维护成本，证据不足

INLINE_ACTION_ALLOWED = NO（并非全部七项都能给出确定的 YES）
```

**结论：F2 本阶段不实施，全部 DEFER。** 这不是保守回避，是严格执行 PART_10 的门槛——只要有一项不能给出有证据支持的 YES，就必须 DEFER，不能"看起来应该做"就做。STRICT_SCOPE 允许"最多再处理一个 F2"，但没有强制要求必须处理；本阶段选择只做 F1，是审计结果本身导出的结论，不是偷懒。

## 9. 实际 Touch And Migrate

**实际修改文件**：仅 `admin-h5/src/views/MenuManage.vue`（业务代码）+ `admin-h5/scripts/test-phase05b-menu-high-frequency-efficiency.mjs`（新增测试）+ `admin-h5/package.json`（仅注册测试命令）。未修改 API、数据库、菜品数据模型、消费者菜单合同、分类业务规则、上下架业务语义、价格计算、库存业务规则、图片上传链路。

**实际修改点**：

1. 新增 `const searchKeyword = ref('')`。
2. `filteredCategories` computed：搜索时忽略 `activeCategory`，改为返回"有真实匹配菜品的分类列表"（OPTION B）；不搜索时行为完全不变。
3. `dishesByCategory(cat)`：搜索时在原有按分类过滤的基础上，再按名称包含关键词过滤；不搜索时行为完全不变。
4. 模板新增 `a-input-search` 搜索框（分类筛选上方）。
5. 模板新增"搜索无结果"独立空态分支，语义与"真实无菜品"/"加载失败"三态分离。
6. "全部上架/全部下架"按钮搜索时隐藏，避免批量操作范围歧义。

未触碰：分类排序（拖拽/箭头）、批量管理、图片压缩、菜品库业务、AI 生成、库存系统、SKU、菜品详情页、消费者菜单、性能、数据库索引、CustomerList、OrderManage。

## 10. TDD RED → GREEN

新增 [test-phase05b-menu-high-frequency-efficiency.mjs](../../admin-h5/scripts/test-phase05b-menu-high-frequency-efficiency.mjs)，覆盖 PART_15 要求的 7 项测试（编号沿用 PART_15 的 TEST 1-7；TEST 0 是行为镜像与真实源码一致性的前置校验，防止镜像逻辑跟实现脱节导致的假通过）。

### RED（对迁移前真实源码验证，方法：`git show BASELINE_SHA:...` 输出到临时文件后跑同等断言，未使用 stash，未触碰工作区任何文件，验证完成后临时文件已删除）

```text
FAIL 1. Main list search input exists
FAIL 4. Distinct search-no-result branch exists
FAIL 6. filteredCategories ignores activeCategory while searching (OPTION B)
RED-check failures (expected on baseline): 3
```

### GREEN

```text
$ npm run test:phase05b-menu-high-frequency-efficiency
PASS 0. The mirror above matches the real dishesByCategory/filteredCategories source verbatim
PASS 1. The main dish list supports a real name search, wired to its own state -- distinct from the library-import search
PASS 2. Matching a keyword only shows dishes whose real name contains it
PASS 3. Clearing the keyword restores the normal, unfiltered category view
PASS 6. Search ignores the active category (OPTION B) -- a real dish in another category is still found
PASS 7. Search never mutates the underlying allDishes array
PASS 4. A real search-no-result state is distinct from the true-empty-menu state
PASS 5. A load failure still renders Phase-03C's Error state and is not masked by the new search-no-result branch
Phase-05B menu high-frequency efficiency: passed
```

`NO_PRODUCT_RED` 不适用——F1（主列表搜索）在迁移前是真实缺失的能力，测试 1/4/6 走了真实 RED；测试 2/3/7 依赖的过滤函数迁移前也不存在等价逻辑，同样是有意义的新增覆盖，不是回归锁。

### 测试质量说明（TEST_QUALITY，PART_15 要求）

测试没有只断言源码包含字符串 `"searchKeyword"`。TEST 0 先锁定"行为镜像与真实实现逐字一致"，随后 TEST 2/3/6/7 用真实的四菜品/三分类夹具数据跑这个镜像函数，验证的是"真实展示集合确实由搜索条件控制"这件事本身（比如验证"宫保鸡丁"和"可乐鸡翅"能被"鸡"匹配到，"清炒时蔬"不能），而不是字符串是否出现。局限：仓库没有 Vue render test framework，无法验证 `<a-input-search>` 在真实浏览器里输入时是否触发预期的响应式更新链路（`v-model:value` 到 computed 重新求值），这部分由 Vue 自身的响应式系统保证，未做超出源码级验证之外的运行时断言。

## 11. Regression Gates

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `npm run test:phase05b-menu-high-frequency-efficiency` | 8/8 PASS |
| 2 | `npm run test:phase03c-dish-state-truthfulness` | 6/6 PASS |
| 3a | `node scripts/test-onboarding-continuation.mjs` | ok |
| 3b | `node scripts/test-performance-observability.mjs` | 11/11 PASS |
| 4 | `npm run test:phase04-component-adoption-governance` | 6/6 PASS（与 MenuManage 无直接交集，确认未受影响） |
| 5 | `npm run check` | 全链路通过，含以上全部已注册测试 |
| 6 | `npm run build` | `✓ built in 19.41s`，无编译错误，`MenuManage-*.js` chunk 从 39.81 kB 增长到 40.47 kB，与新增的搜索逻辑体量吻合 |

```text
NEW_FAILURE = 0
```

未发现新的测试失败。已用 `grep -rl "MenuManage.vue" scripts/*.mjs` 确认涉及 `MenuManage.vue` 的全部测试文件（`test-onboarding-continuation.mjs`、`test-performance-observability.mjs`、`test-phase03c-dish-state-truthfulness.mjs`、本阶段新增文件）均已在上表覆盖，不存在 Phase-05A 那种"未注册进 `npm run check` 的既有测试"的遗留情况。

## 12. Browser Verification

```text
BROWSER_VERIFICATION=NOT_RUN
REASON=本机没有可用于 MenuManage 的登录态或可用的开发/staging 后端（需要真实商家账号 + 真实菜品数据才能观察到搜索框的实际交互效果）。`npm run build` 已确认模板/脚本改动可以正确编译成生产构建。自动化合同测试（第 10 节）用真实数据夹具验证了过滤逻辑本身的正确性，不用浏览器验证冒充完成。
```

## 13. Before / After Efficiency

### BEFORE

```text
TASK = 找到一道已知名称的菜品
SEARCH_AVAILABLE = NO
SCROLL_COST = MEDIUM-HIGH（无搜索、无虚拟滚动，取决于分类内菜品数量）
CATEGORY_DEPENDENCE = HIGH（唯一的缩小范围手段）
DISCOVERY_STEPS = 判断分类（1 次决策）→ 可选点击分类（0-1 次点击）→ 肉眼扫描/滚动全部菜品行（N 次决策，N 随菜品数量增长）
```

### AFTER

```text
SEARCH_AVAILABLE = YES
TARGET_DISCOVERY_STEPS = 点击搜索框（1 次点击）→ 输入菜名（1 次输入）→ 目标菜直接出现在结果里（0 次额外决策，除非搜索词命中多个菜品）
SCROLL_COST = LOW（结果集通常远小于全量菜单）
CATEGORY_DEPENDENCE = NONE（OPTION B：搜索跨越全部分类，不再依赖老板记得/选对分类）
```

不是"体验更好了"这种模糊结论：DISCOVERY_STEPS 从"N 随菜品总数增长的线性扫描"变成"1 次输入 + 常数级结果查看"；CATEGORY_DEPENDENCE 从 HIGH 降到 NONE，直接消除了 PART_05 指出的"因为忘记自己在哪个分类导致系统说没有这道菜"这一类风险。

## 14. Scope Audit

```text
SCOPE_EXPANDED = NO
```

逐条核对 STRICT_RULES 1-21：未改后端 API/数据库/菜品数据模型/消费者菜单合同/分类业务规则/上下架业务语义/价格计算/库存业务规则；未新增批量编辑系统/高级筛选系统/新搜索服务/Elasticsearch 等搜索基础设施（第 5 节已证明本地搜索足够，不需要）；未做性能专项/虚拟滚动；未改图片上传链路；未重构整个 MenuManage（改动集中在 2 个 computed/function 和 3 处模板片段）；未建立第二套组件库；未扩大 Vant（本阶段唯一新增 UI 是 Ant 的 `a-input-search`）；未顺手处理分类排序拖拽/箭头问题（第 15 节记录为 DEFER）；未顺手处理所有菜品编辑体验问题（F2 全部 DEFER，第 8 节已说明理由）；未为了少一步取消任何必要确认（删除菜品的二次确认、售罄的无确认高频动作均未改动）。

## 15. Deferred Issues

只记录，本阶段不实现：

1. **F2 全部候选（价格/分类/名称/图片内联编辑）**（第 8 节已详述）：INLINE_ACTION_GATE 未能给出全部 YES，按门槛规则 DEFER。
2. **分类排序"拖拽/箭头"文案与实现不符**（Phase-05 报告已记录，DO_NOT_TOUCH 第 1 项明确排除）：本阶段确认未处理。
3. **菜品库导入的搜索体验**（本阶段确认它是独立于本次修复的另一套搜索，未做任何改动，也不在 STRICT_SCOPE 内）。
4. **搜索结果跨分类分组展示的进一步优化**（比如是否需要一个"搜索结果"虚拟分组标题而不是复用真实分类名）：当前实现复用真实分类头部展示搜索结果，已通过测试验证语义正确，如果未来有真实商家反馈这种呈现方式造成困惑，再单独评估，本阶段不预先优化。
5. **搜索框在多设备/极端窄屏下的位置与现有页头按钮的视觉挤压问题**：未做浏览器验证（第 12 节已说明原因），如有真实反馈再处理。

## 16. Phase-05C Input

下一阶段 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-05C` 主题是 CustomerList 的搜索/分页/详情往返状态保持——核心问题是查完一个会员、进详情页再返回列表后，搜索关键词、已加载页数、筛选条件全部丢失，前台连续核对多个顾客时必须每次从零开始搜索。05C 必须先做状态保存的技术方案评估（本报告不预先展开，也不预先假定方案就是全局 `keep-alive`——Phase-05 的原始审计已经指出这个问题的修复成本比看起来更高，需要独立评估）。本报告不在这里开始实施。

## ACCEPTANCE

1. **老板现在是否可以按菜名快速找到目标菜？** 可以。第 13 节：从"线性扫描 N 道菜"变成"输入关键词，常数级查看结果"。
2. **搜索的是当前门店菜单，而不是菜品库吗？** 是。第 4 节已明确区分 `MAIN_MENU_SEARCH`（本阶段新增，作用于 `allDishes`）和 `LIBRARY_SEARCH`（既有，作用于 `searchDishLibrary` 返回的其它商户分享内容），第 10 节测试 1 用真实断言锁定了 `searchKeyword`/`libraryKeyword` 是两个独立的 ref。
3. **搜索是否基于真实完整数据源？** 是。第 5 节已用只读核实确认 `GET /menu/items` 无分页、无行数限制，`allDishes` 就是完整门店菜单。
4. **是否避免了"搜不到其实存在的菜"的假搜索？** 是。第 6 节选择 OPTION B（搜索跨越全部分类），第 10 节测试 6 用真实数据验证了"素菜"分类下搜索一个实际属于"招牌菜"的菜名仍能找到。
5. **搜索无结果、真实空菜单、加载失败是否严格区分？** 是。第 7 节和第 10 节测试 4/5：三种状态有各自独立的判断条件和文案，求值顺序保证加载失败优先于搜索无结果，搜索无结果优先于（但不会被误判为）真实空菜单。
6. **分类和搜索的组合规则是否清晰？** 是。第 6/7 节：搜索时跨分类查找、忽略当前 tab；搜索结果仍按真实分类分组展示；分类批量上下架按钮在搜索时隐藏，避免范围歧义。
7. **搜索是否没有建立第二份菜品状态？** 是。第 10 节测试 7 用真实断言验证了过滤前后 `allDishes` 不受任何修改，且源码里没有一个独立的 `displayedDishes` 副本 ref。
8. **是否保持 Phase-03C 状态真实性？** 是。`loadError`/`loadingMenu`/三态空态判断链路完全未改动，只是在其后追加了一个新的搜索无结果分支，第 10 节测试 5 专门验证了这一点。
9. **是否没有为了搜索扩建后端？** 是。第 5 节已证明现有后端能力（无分页、全量返回）足够支撑本地搜索，未新增任何 API、未触碰 `saas-base`。
10. **是否审计了最高频的小修改路径？** 是。第 8 节逐项审计了上下架/售罄/价格/分类，明确售罄已经高效，其余不满足实施门槛。
11. **F2 如果实施，是否通过 INLINE_ACTION_GATE？** 不适用——F2 本阶段未实施，第 8 节已完整展示门槛评估过程和未通过的具体原因。
12. **是否最多只解决 1~2 个真实摩擦？** 是。只解决了 1 个（F1 菜品搜索）。
13. **是否没有扩大到批量编辑/分类排序/图片/库存重构？** 是。第 14 节 Scope Audit 已逐条核对。
14. **是否完成真实 RED → GREEN 或诚实记录 NO_PRODUCT_RED？** 完成了真实 RED → GREEN（第 10 节），未使用 `NO_PRODUCT_RED`（因为 F1 是真实缺失的能力，不存在"已经合规不需要造假 RED"的情况）。
15. **是否能用步骤/查找成本证明效率提升？** 是。第 13 节给出了具体的 DISCOVERY_STEPS/SCROLL_COST/CATEGORY_DEPENDENCE 量化对比，不是"体验更好了"这种模糊结论。

```text
FINAL_DECISION=RESULT A: MENU_HIGH_FREQUENCY_EFFICIENCY_READY
MENU_NAME_SEARCH=READY
SEARCH_DATA_SOURCE=allDishes（GET /v1/menu/items 一次性返回的完整门店菜单，本地过滤，无第二数据源）
SEARCH_SCOPE=CURRENT_TENANT_MENU
PHASE03C_TRUTHFULNESS=PRESERVED
SECONDARY_FRICTION=DEFERRED（F2 全部候选均未通过 INLINE_ACTION_GATE）
BACKEND_API_CHANGED=NO
DATABASE_CHANGED=NO
SCOPE_EXPANDED=NO
```

## COMMIT_RULE

```text
CHANGED_FILES=
  admin-h5/package.json
  admin-h5/src/views/MenuManage.vue
  admin-h5/scripts/test-phase05b-menu-high-frequency-efficiency.mjs（新增）
  docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE05B_MENU_HIGH_FREQUENCY_EFFICIENCY.md（新增，本文件）
  PROJECT_INDEX.md
  PROJECT_KNOWLEDGE_MAP.md
STAGED_FILES=同上，仅这 6 个文件
UNRELATED_WIP_INCLUDED=NO
```

下一阶段进入 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-05C`，页面为 CustomerList，核心问题是搜索/分页/详情页往返后用户工作上下文丢失，必须先做状态保存技术方案评估，不预先假定全局 `keep-alive`。
