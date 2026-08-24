# Admin Performance Observability Phase 02 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不发送网络请求、不改变业务流程和 API 协议的前提下，为 admin-h5 四个高频页面建立可信的页面与核心 API 性能事件。

**Architecture:** 新增一个无第三方依赖的事件收集模块，提供统一 schema、有界队列、开发态 console、订阅出口、页面访问上下文和 API 计时。Router 负责页面进入起点，四个页面只标记真实业务内容完成边界，Axios 拦截器集中标记核心 API start/end。Vite 在构建时注入实际 checkout SHA。

**Tech Stack:** Vue 3、Vue Router 4、Axios、Vite 5、Node.js 内置 test/assert。

---

### Task 1: 先建立失败的性能事件合同测试

**Files:**
- Create: `admin-h5/scripts/test-performance-observability.mjs`

- [ ] **Step 1: 写事件、队列、页面和 API 行为测试**

测试直接导入预期模块，并定义期望 API：

```js
import {
  createAdminPerformanceCollector,
  classifyAdminApiFailure,
} from '../src/utils/adminPerformance.js'

const collector = createAdminPerformanceCollector({
  environment: 'local',
  version: 'f7464e83efeab28f9360a9d6149cadae116d2e27',
  now: () => wallClock,
  clock: () => monotonicClock,
  scheduleAfterRender: callback => callback(),
})
```

必须断言：统一字段完整；队列最多 200 条；订阅可取消；四个页面均产生 enter/content/ready 且 content/ready 幂等；orders/menu/members/marketing API 产生 start/end；成功与各类失败可区分；源码接线存在；采集模块不包含网络发送调用。

- [ ] **Step 2: 运行测试并确认 RED**

Run: `node --test scripts/test-performance-observability.mjs`（工作目录 `admin-h5`）  
Expected: FAIL，原因是 `src/utils/adminPerformance.js` 尚不存在，而不是测试语法错误。

### Task 2: 实现统一事件核心与构建版本

**Files:**
- Create: `admin-h5/src/utils/adminPerformance.js`
- Modify: `admin-h5/vite.config.js`

- [ ] **Step 1: 实现纯事件收集器**

模块必须导出：

```js
export function createAdminPerformanceCollector(options) {}
export function beginPageNavigation(route) {}
export function completePageNavigation(route, failure) {}
export function markPageContentReady(details) {}
export function startAdminApiRequest(config) {}
export function finishAdminApiRequest(trace, result) {}
export function classifyAdminApiFailure(error) {}
export function subscribePerformanceEvents(listener) {}
export function getPerformanceEvents() {}
export function clearPerformanceEvents() {}
```

收集器始终生成核心字段，使用 `performance.now()` 计算 duration，使用 `Date.now()` 生成 timestamp；事件冻结后进入最大 200 条 FIFO 队列。监听器异常不得传播。`markPageContentReady` 必须绑定当前 visit，并在渲染调度后各产生一次 content 与 ready。

- [ ] **Step 2: 实现 API 匹配与隐私归一化**

只匹配以下路径族：

```js
const API_GROUP_RULES = [
  ['orders', /^\/v1\/orders(?:\/|$)/],
  ['menu', /^\/v1\/(?:menu|dish-library)(?:\/|$)/],
  ['members', /^\/v1\/(?:customers|membership)(?:\/|$)/],
  ['marketing', /^\/v1\/(?:coupons?|coupon-templates|marketing)(?:\/|$)/],
]
```

另将 `/v1/tenant/marketing-preview` 与 `/v1/stats/marketing-effectiveness` 归入 marketing。request name 使用 HTTP method 与去查询、去 origin、动态 ID 替换后的 endpoint。

- [ ] **Step 3: 注入实际 checkout SHA**

在 Vite 配置中使用 `execFileSync('git', ['rev-parse', 'HEAD'])` 获取实际构建源码，显式 `ADMIN_RELEASE_SHA` 优先，git 结果次之，`GITHUB_SHA` 只作最后回退。通过 `define.__ADMIN_BUILD_VERSION__` 注入完整 SHA。

- [ ] **Step 4: 运行合同测试**

Run: `node --test scripts/test-performance-observability.mjs`  
Expected: 核心合同用例通过；接线相关用例仍失败，证明后续任务尚未实现。

### Task 3: 接入 Router 与四个页面业务锚点

**Files:**
- Modify: `admin-h5/src/router/index.js`
- Modify: `admin-h5/src/views/Dashboard.vue`
- Modify: `admin-h5/src/views/OrderManage.vue`
- Modify: `admin-h5/src/views/MenuManage.vue`
- Modify: `admin-h5/src/views/CustomerList.vue`

- [ ] **Step 1: Router 建立页面访问上下文**

在现有鉴权 guard 之前注册独立性能 beforeEach，并在 afterEach 完成页面进入：

```js
router.beforeEach((to) => {
  beginPageNavigation(to)
  return true
})
router.afterEach((to, _from, failure) => {
  completePageNavigation(to, failure)
})
```

不得修改现有鉴权 guard 的条件和 next 分支。

- [ ] **Step 2: Dashboard 标记主统计完成**

在 `loadStats()` 的 finally 中、`statsLoaded=true` 后调用 `markPageContentReady`，status 来自 `statsError`，data count 来自当前订单数量。轮询重复调用由 visit 幂等规则抑制。

- [ ] **Step 3: OrderManage 标记首次同步完成**

复用现有 `watch`，只在 `initialLoading` 发生 `true -> false` 后标记。status 由 `syncFailed` 与 orders 数量计算。不得增加一次同步请求。

- [ ] **Step 4: DishManage 与 MemberManage 标记首次加载完成**

两个 load 函数用局部 `resultStatus` 记录 success/empty/error，finally 中调用统一标记；不得改变现有页面状态或提示分支。

- [ ] **Step 5: 运行页面采集测试**

Run: `node --test scripts/test-performance-observability.mjs`  
Expected: 页面进入、首屏、ready 与幂等用例通过。

### Task 4: 在 Axios 拦截器集中采集 API 性能

**Files:**
- Modify: `admin-h5/src/api/request.js`

- [ ] **Step 1: 请求拦截器生成本地 trace**

在现有 `config.meta` 中新增 `performanceTrace`，通过 `startAdminApiRequest` 产生 start 事件。不设置请求头，不修改 data/params，不匹配的 API 返回 null。

- [ ] **Step 2: 成功响应记录 end**

在返回 raw response 或 data 之前调用 `finishAdminApiRequest`。business status 兼容现有 `code` 和治理合同 `success`；payload size 只读取响应 Content-Length。

- [ ] **Step 3: 所有错误路径记录 end**

在 duplicate return、401 跳转和原错误处理之前完成性能终态。错误分类必须保留原 Promise reject、localStorage 清理和 message 行为。

- [ ] **Step 4: 运行 API 成功/失败测试**

Run: `node --test scripts/test-performance-observability.mjs`  
Expected: success、business_error、http_error、network_error、timeout、cancelled、duplicate_skipped 全部通过。

### Task 5: 接入项目测试命令并完成局部验证

**Files:**
- Modify: `admin-h5/package.json`

- [ ] **Step 1: 新增测试脚本并纳入 check**

```json
"test:performance-observability": "node --test scripts/test-performance-observability.mjs"
```

在 `check` 的构建前运行该测试，不新增依赖。

- [ ] **Step 2: 运行新增测试**

Run: `npm run test:performance-observability`  
Expected: 全部通过，退出码 0。

- [ ] **Step 3: 编译所有受影响 Vue 文件**

使用项目已有 `@vue/compiler-sfc` 对四个文件执行 parse、compileScript、compileTemplate。  
Expected: 4/4 文件均无 parse、script、template 错误。

### Task 6: 补全实施文档并做最终验证

**Files:**
- Modify: `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE02_IMPLEMENTATION.md`

- [ ] **Step 1: 记录真实实施结果**

补充实际修改文件、事件字段、采集位置、真实测试命令与结果、限制、五项验收回答和 L1 -> L2 决策。不得填写运行时性能数值。

- [ ] **Step 2: 运行完整前端检查**

Run: `npm run check`（工作目录 `admin-h5`）  
Expected: 所有脚本和 production build 退出码 0；如存在既有 warning，原样记录但不宣称清除。

- [ ] **Step 3: 运行独立 production build**

Run: `npm run build`（工作目录 `admin-h5`）  
Expected: 退出码 0，构建版本使用当前实际 HEAD。该命令只用于本地验证，不构成生产部署建议。

- [ ] **Step 4: 审计变更白名单**

Run: `git status --short`、`git diff --check`、`git diff --name-only <design-commit>`  
Expected: 没有后端、数据库、API contract、依赖或无关页面变更；保留任务开始前既有未提交文件。

