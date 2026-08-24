# 菜品管理状态真实性 Touch And Migrate（Phase-03C）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03C
STATUS=DISH_MANAGE_STATE_TRUTHFULNESS_MIGRATION
PREVIOUS_PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-03B
REFERENCE=ADMIN_FRONTEND_CONSTITUTION.md V1.0, ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md, ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md
REPOSITORY_BASELINE_SHA=c37f3beb5af8cc06a7831e4e75b6bea4b44f0cbb
SCOPE=admin-h5/src/views/MenuManage.vue（状态展示逻辑）
BUSINESS_CODE_CHANGE=YES（loadMenu 与 doLibrarySearch 的失败判定与失败态展示，见第 3/4 节）
API_CHANGE=NO
DATA_STRUCTURE_CHANGE=NO
NEW_FEATURE=NO
BULK_EDIT=NO
IMAGE_OPTIMIZATION=NO
PERFORMANCE_OPTIMIZATION=NO
FULL_PAGE_REWRITE=NO
```

## 0. 文件名映射说明

REFERENCE 和 FILES_SCOPE 使用的页面名是产品语义上的 "DishManage"，但仓库里没有 `admin-h5/src/views/DishManage.vue` 这个文件。对照 [ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md §1.7](./ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md) 的文件规模表（"MenuManage.vue | 约 1539 行"）和 [ADMIN_FRONTEND_CONSTITUTION.md §5.2](./ADMIN_FRONTEND_CONSTITUTION.md)（"菜品"业务规则），实际承载"菜品管理" Job 的文件是 `admin-h5/src/views/MenuManage.vue`（当前 1547 行）。本报告和新增测试全部针对这个真实文件；下文继续用"菜品管理/DishManage"指代这个页面的产品身份，代码引用统一写 `MenuManage.vue`。

## 1. DishManage Jobs 分析

沿用并落实 [ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md §2.2](./ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md) 已定义的 DishManage Jobs：

- **用户**：老板 / 店长。
- **任务**：供应、价格或商品信息变化时，快速找到目标菜品并完成维护。
- **成功标准**：老板打开菜品管理后，能确定四件事——当前有哪些菜、哪些菜正常售卖、是否存在加载异常、是否需要处理——而不是先看到一个真假难辨的菜单。
- **核心动作**：搜索定位、改价、售罄/恢复、上下架。
- **禁止展示**：加载失败显示为空菜单；找不到目标菜品时无任何引导。

菜品管理是核心链路的第一环（菜品管理 → 消费者菜单 → 用户点餐 → 订单收入）。如果这一环的状态本身不可信，老板既可能误以为菜品被清空而恐慌重新上架，也可能误以为加载失败只是"店里确实还没有菜"而忽略真实的接口故障——两种误判都会直接影响顾客能不能点到本该在售的菜。

## 2. 当前问题审计

按 CURRENT_AUDIT 的六个检查点，逐条核对当前 `MenuManage.vue` 真实源码（迁移前的状态）：

### 2.1 菜品首次加载失败 —— 不符合，P0

`loadMenu()`（迁移前）：

```js
async function loadMenu() {
  loadingMenu.value = true
  let resultStatus = 'success'
  try {
    const res = await getMenuItems()
    const raw = res?.data?.data?.items || res?.data?.items || res?.data || []
    allDishes.value = Array.isArray(raw) ? raw.map(...) : []
    resultStatus = allDishes.value.length ? 'success' : 'empty'
  } catch {
    allDishes.value = []
    resultStatus = 'error'
  } finally {
    loadingMenu.value = false
    markPageContentReady({ page: 'DishManage', status: resultStatus, data_count: allDishes.value.length })
  }
}
```

`resultStatus` 三态齐全（success/empty/error），但**只喂给了 `markPageContentReady`——一个内部性能埋点，商家完全看不到**。页面模板只有 `v-if="loadingMenu"` → `v-else-if="allDishes.length === 0"` → `v-else`（列表）三段，没有任何 error 分支。无论是"确实没有菜"还是"接口挂了"，商家看到的都是同一句"还没有菜品，点右上角「加菜品」开始上架"，外加一个"添加第一道菜"按钮——这正是 Phase-01 §2.1 早就点名的 P0 问题，本次审计确认它仍然存在于当前代码中，不是历史结论。

更严重的是 `catch` 分支会**主动清空** `allDishes.value = []`。这意味着如果初次加载成功、后来因为某次动作失败触发的重新加载（[MenuManage.vue:803](../../admin-h5/src/views/MenuManage.vue)、[:846](../../admin-h5/src/views/MenuManage.vue) 的 `catch { message.error('操作失败'); await loadMenu() }`）又失败，会把已经正确显示的真实菜单**清空**成误导性的空态，比"什么都不做"更危险。

### 2.2 隐藏的第二个问题：业务失败不会进入 catch，直接被当成空菜单

`getMenuItems()` 请求成功但业务失败（HTTP 200，envelope `code !== 200`，例如未登录或缺少门店参数，见 [saas-base/app/api/v1/menu.py:259,269](../../saas-base/app/api/v1/menu.py)）时，`res?.data?.data?.items || res?.data?.items || res?.data || []` 这条兜底链不会抛出异常——`res?.data` 在业务失败时通常是 `null`/未定义，链条一路兜底到 `[]`，`Array.isArray([]) === true`，于是 `allDishes.value = []`、`resultStatus = 'empty'`。**这类失败连 `catch` 分支都不会进入**，是比 2.1 更隐蔽的一种"失败=空菜单"。修复 2.1 时必须一并堵住这条路径，否则加了 error 状态也接不住这种失败。

### 2.3 分类加载失败 —— 架构上不存在独立故障面

`categories`（[MenuManage.vue:634](../../admin-h5/src/views/MenuManage.vue)）是从 `allDishes.value` 现算的 `computed`，不存在独立的"分类列表接口"。唯一涉及分类的网络请求是 `loadCategoryOrder()`（[:871](../../admin-h5/src/views/MenuManage.vue)，读取商家自定义的分类排序偏好），失败时静默保留默认顺序，不影响哪些分类会出现——不会隐藏或虚构任何分类。**结论：2.1/2.2 修好之后，分类显示自动跟着可信；不需要为"分类"单独造一个 error 状态，那样反而是无中生有的伪合同。**

### 2.4 空菜单判断 —— 依赖 2.1 的修复

当前 `allDishes.length === 0` 同时对应"真的没有菜""接口失败""业务失败"三种情况，无法区分。这是 2.1/2.2 的直接后果，不是独立问题。

### 2.5 搜索失败 —— 不符合，与主列表同一模式的缺陷

`MenuManage.vue` 的主菜品列表本身没有按名称搜索（这是 Phase-01 §2.2 记录的 P1 效率问题，SCOPE 明确不允许本阶段新增），唯一的"搜索"是"菜品库导入"抽屉里搜索其他商户分享的菜品库（`doLibrarySearch`，[:984](../../admin-h5/src/views/MenuManage.vue)）。迁移前：

```js
async function doLibrarySearch() {
  librarySearching.value = true
  try {
    const res = await searchDishLibrary({...})
    libraryItems.value = res?.data?.data || res?.data || []
  } catch { libraryItems.value = [] }
  finally { librarySearching.value = false }
}
```

同样的模式：失败清空为 `[]`，模板对 `libraryItems.length === 0` 只有一句"还没有商户分享过这道菜，先自己上传吧"，无法区分"真的没人分享"和"搜索请求失败"。如果老板正在浏览已经搜出来的结果，改一个关键词时网络抖了一下，会把已经在看的正确结果替换成这句误导文案。**结论：不符合，与 2.1 同一类问题，本阶段一并修复。**

### 2.6 刷新反馈 —— 不适用（无手动刷新入口），修复后新增

`MenuManage.vue` 没有下拉刷新或"刷新"按钮——`loadMenu()` 只在 `onMounted`、AI 导入成功后、菜品库导入成功后被调用（[:943](../../admin-h5/src/views/MenuManage.vue)、[:1016](../../admin-h5/src/views/MenuManage.vue)）。在本阶段修复 2.1 之前，加载失败根本没有任何"重试"入口——因为压根没有 error 状态可以挂重试按钮。**这意味着 TDD_REQUIREMENT 第 5 条（刷新失败要有明确反馈）在迁移前无法测试，因为"刷新"这个动作本身不存在**；本阶段在新增的 error 状态里补上重试按钮（调用 `loadMenu()`/`doLibrarySearch()`），这个重试入口本身就是本页面当前唯一的"手动刷新"，修复后可以测试。

### 2.7 数据真实性 —— 修复后符合

菜品数量、分类数量均来自 `allDishes`（真实接口数据）现算，没有前端默认推导虚构数字；本阶段的修复进一步堵住了"业务失败被当作 0 条真实数据"这条路径（见 2.2）。

## 3. 修改方案

采用最小迁移，只动状态判断和展示逻辑，不动数据结构、不动业务流程：

1. **`loadMenu()`**：新增 `if (res?.code !== 200) throw ...` 业务失败判定（对齐 Dashboard.vue/OrderManage.vue 已经验证过的模式）；`catch` 分支不再清空 `allDishes`，只置 `loadError.value = true`。
2. **模板**：仿照 [OrderManage.vue 的既有状态合同](./ADMIN_FRONTEND_SYSTEM_PHASE03A_ORDER_STATE_MIGRATION.md) 拆成四段——① `loadError && allDishes.length > 0` 时显示"当前显示的是上次数据"的常驻警示条（旧数据仍在下方渲染，不隐藏）；② `loadError && allDishes.length === 0` 时显示独立错误态；③ `loadingMenu && allDishes.length === 0` 骨架屏；④ 确认成功且 0 条才是空态；⑤ 其余情况渲染列表。
3. **`doLibrarySearch()`**：同样的失败判定和"不清空旧结果"处理，模板补一个 `libraryError` 分支。
4. 新增 `loadError`、`libraryError` 两个 `ref`，均默认为 `false`；除此以外不新增任何状态变量、不新增按钮以外的交互、不改动数据结构。

选择最小迁移而非更大范围重写的原因：STRICT_RULES 明确禁止批量编辑、图片优化、性能优化、大型组件抽取、整页重构；本阶段的 Job 是"让老板相信后台显示的信息"，这只需要状态判断正确，不需要改变菜品管理的任何交互形态。

## 4. 状态合同变化

| 状态 | Before | After |
| --- | --- | --- |
| 首次加载失败（无旧数据） | **不符合**：`allDishes` 被清空为 `[]`，模板落入"还没有菜品"空态，附带"添加第一道菜"按钮，直接鼓励老板重新建菜 | **符合**：`loadError && allDishes.length===0` 渲染独立 error alert（"菜品加载失败，请检查网络后重试" + 重试按钮），不进入空态 |
| 重新加载失败（已有旧数据） | **不符合**：同样清空为 `[]`，把已经正确显示的菜单变成假空态 | **符合**：`loadError && allDishes.length>0` 显示"菜品同步失败，当前显示的是上次数据"警示条，旧菜单继续渲染在下方 |
| 业务级失败（HTTP 200，`code!==200`） | **不符合**：不触发 `catch`，直接沿兜底链落到 `[]`，`resultStatus='empty'`，连内部埋点都记错 | **符合**：显式 `throw`，进入统一的 loadError 路径，内部埋点也正确记为 `error` |
| 成功返回 0 条 | 已符合：`resultStatus='empty'`，但用户侧和"失败"用同一个空态视觉，无法区分 | 符合且可区分：`loadError=false` 时才会走到空态分支，与失败态视觉、文案均不同 |
| 分类显示 | 未发现独立缺陷（架构上依附于 allDishes） | 无变化，随 2.1/2.2 的修复自动可信 |
| 菜品库搜索失败 | **不符合**：清空为 `[]`，与"没人分享过"用同一句文案 | **符合**：`libraryError` 独立分支，保留上一次正确结果，提供重试 |
| 手动刷新/重试 | **不适用**：没有任何重试入口 | **新增能力**：两处菜单错误态、一处搜索错误态均提供重试按钮，调用与初始加载相同的 `loadMenu()`/`doLibrarySearch()` |

## 5. TDD 结果

### RED（对迁移前源码的真实验证，不是推测）

新增测试文件 [test-phase03c-dish-state-truthfulness.mjs](../../admin-h5/scripts/test-phase03c-dish-state-truthfulness.mjs) 先针对**未修改的原始 `MenuManage.vue`**（通过 `git stash` 临时还原验证，而不是假设）运行：

```text
FAIL 1. First dish-list load failure resolves to Error, not an empty menu
FAIL 2. Dish list loading successfully with zero dishes resolves to Empty
PASS 3. Category display has no separate failure surface to lie about
FAIL 4. Library search failure preserves the previous results and reports failure...
FAIL 5. Retry after a failure re-runs the same guarded load and can report failure again...
FAIL 6. A successful load with real dishes resolves to Success
Phase-03C RED failures: 5
```

用例 3 一次性 PASS，因为它验证的是"分类没有独立故障面"这个架构事实（第 2.3 节），迁移前后都成立，不是缺陷。其余 5 个用例在迁移前源码上如期 FAIL，证明测试确实在检验真实行为而不是空断言。

### GREEN

修复第 3 节的改动后，`git stash pop` 恢复修改，重新运行：

```text
$ npm run test:phase03c-dish-state-truthfulness
PASS 1. First dish-list load failure resolves to Error, not an empty menu
PASS 2. Dish list loading successfully with zero dishes resolves to Empty
PASS 3. Category display has no separate failure surface to lie about
PASS 4. Library search failure preserves the previous results and reports failure, not a false "nothing shared" empty state
PASS 5. Retry after a failure re-runs the same guarded load and can report failure again
PASS 6. A successful load with real dishes resolves to Success
Phase-03C dish state truthfulness: passed
```

### 回归测试

```text
$ npm run test:onboarding-continuation      → ok（新手引导流程会经过 loadMenu()，未受影响）
$ npm run test:performance-observability    → 11/11 pass（markPageContentReady 埋点字段/调用点未改动）
```

未运行 `npm run build`：本阶段改动是状态判断逻辑和纯文本/按钮的模板分支，不涉及依赖、类型或构建配置。

## 6. 风险评估

- **菜品业务未被改变**：`getMenuItems`、`searchDishLibrary` 的调用参数、`allDishes`/`libraryItems` 的数据形状、菜品的增删改查、上下架、售罄逻辑均未触碰；本阶段只改变了"请求失败时该展示什么"和"失败要不要清空已经正确的数据"。
- **`res?.code !== 200` 判定的依据**：通过只读方式核实了 `saas-base/app/api/v1/menu.py` 的响应封装（`RespVo{code,msg,data}`，业务失败以 HTTP 200 + `code!=200` 返回，不抛 `HTTPException`）和 `admin-h5/src/api/request.js` 的拦截器行为（原样返回 `response.data`，即整个 envelope），确认 `res.code`（而不是 `res.data.code`）是正确的失败判定字段，且与 `Dashboard.vue` 已验证过的写法完全一致，不是本阶段发明的新约定。
- **回归风险低**：改动集中在两个函数的 `try/catch` 内部判定和对应的模板分支；`allDishes`/`libraryItems` 的写入时机、菜品增删改的调用路径均未改动。移除 `catch` 里的清空操作是本阶段风险最高的一处改动，已通过 RED→GREEN 验证：迁移前"清空成空态"和迁移后"保留旧数据+警示条"两种行为都被测试明确锁定，不存在"看起来改了但没测到"的空白。
- **测试方法论的教训（延续自 Phase-03B）**：本次没有重犯 CRLF 切片的错误——直接在读取源码时 `.replace(/\r\n/g, '\n')`；同时为了让 RED 阶段是"证据"而不是"推测"，用 `git stash` 真实还原了迁移前的文件跑了一遍测试，而不是像 Phase-03A 那样仅凭代码审查断言"如果错了会失败"。

## ACCEPTANCE：验收回答

1. **接口失败是否还会显示空菜单？** 不会。首次加载失败（无旧数据）渲染独立 error alert，不进入空态；业务级失败（HTTP 200 但 code≠200）现在会被显式 `throw`，同样进入 error 路径，不再沿兜底链滑落成"0 条=空菜单"。
2. **老板是否能区分无菜品和系统异常？** 能。空态只在 `loadError===false` 且 `allDishes.length===0` 时出现，文案是"还没有菜品，点右上角「加菜品」开始上架"；系统异常显示"菜品加载失败，请检查网络后重试"（无旧数据）或"菜品同步失败，当前显示的是上次数据"（有旧数据），两者视觉和文案都与空态不同，且都带重试按钮。
3. **分类失败是否有明确反馈？** 分类没有独立的失败面——它是从 `allDishes` 现算的，菜品加载的真实性一旦有保障，分类显示自动跟着可信；用于分类排序偏好的 `loadCategoryOrder()` 失败只影响排序顺序，不隐藏任何分类，属于低风险的良性降级，本阶段确认无需改动。
4. **搜索失败是否保护已有数据？** 是。`doLibrarySearch()` 失败时不再清空 `libraryItems`，上一次的正确搜索结果继续显示，同时通过独立的 `libraryError` 分支明确告知"搜索失败，请检查网络后重试"并提供重试按钮。
5. **是否符合 Phase-02 状态规则？** 符合。Loading/Success/Empty/Error 四态互斥且真实；Unknown 状态在本页面没有对应的具体场景（不存在"无法确认但也不算失败"的中间态，如订单打印结果或打印机连接那种情况），因此没有为了凑合同齐全而虚构一个 Unknown 分支——这符合 Constitution 和 Phase-02 都强调的"不为了统一而统一"。

```text
FINAL_DECISION=RESULT A: DISH_STATE_TRUTHFULNESS_READY
```

本结论确认菜品管理（`MenuManage.vue`）的状态真实性已经达标并被测试锁定，包括迁移前架构上就没有暴露独立故障面的分类显示。菜品主列表缺少按名称搜索、大规模菜品的渲染边界等 Phase-01 §2.2 记录的 P1 效率问题不在本阶段范围内，需要真实任务和性能数据支持后再作为独立任务处理。
