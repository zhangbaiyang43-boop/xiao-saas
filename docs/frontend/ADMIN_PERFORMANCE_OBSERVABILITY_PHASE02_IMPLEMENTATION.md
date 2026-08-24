# admin-h5 最小性能观测 Phase 02 实施记录

> 阶段：P0-ADMIN-PERFORMANCE-OBSERVABILITY-PHASE-02  
> 状态：设计已确认，等待 TDD 实施  
> 基线：`f7464e83efeab28f9360a9d6149cadae116d2e27`  
> 设计确认日期：2026-08-24

## 1. 实施范围

本阶段只在 `admin-h5` 建立最小性能事实采集能力，不优化页面、不改变业务流程、不修改 API 协议或数据库。

覆盖页面：

- Dashboard（路由名 `Dashboard`）
- OrderManage（路由名 `OrderManage`）
- DishManage（当前实现文件与路由名为 `MenuManage`）
- MemberManage（当前实现文件与路由名为 `CustomerList`）

覆盖事件：

- `admin_page_enter`
- `admin_first_content_visible`
- `admin_page_ready`
- `admin_api_request_start`
- `admin_api_request_end`

覆盖 API 业务域：orders、menu/dish、members、marketing。

## 2. 已确认实施设计

### 2.1 事件核心

新增独立、轻量的性能事件模块，承担：

- 统一事件字段和合法枚举。
- 维护最多 200 条事件的有界内存队列。
- 在开发环境输出 `console.info`。
- 提供订阅、读取快照和清空测试数据的出口。
- 所有采集失败静默降级，不允许中断业务。
- 禁止使用 `fetch`、Axios、`sendBeacon` 或其他网络方式发送性能事件。

### 2.2 页面进入

在现有 Vue Router 中集中建立页面访问上下文：

- 导航开始时记录单调时钟起点。
- 导航成功后记录 `admin_page_enter`。
- 导航失败或重定向时不得把失败导航计为成功页面访问。
- 页面映射固定为 `Dashboard`、`OrderManage`、`DishManage`、`MemberManage`。

### 2.3 页面业务锚点

页面只添加最少的显式完成标记，不复制采集实现：

- Dashboard：统计与今日订单第一次结束，并将 success/error 真实状态提交到视图后，记录 first content 与 ready。
- OrderManage：首次订单同步经历 `initialLoading: true -> false`，并将列表、空态或错误态提交到视图后记录；不得为采集增加请求。
- DishManage：第一次 `loadMenu()` 结束并将列表或当前错误结果提交到视图后记录。
- MemberManage：第一次 `loadCustomers()` 结束并将 success、business error 或 request error 结果提交到视图后记录。
- 同一次页面访问的 first content 与 ready 各只产生一次；刷新、轮询和搜索不得重复产生首次页面事件。

### 2.4 API 采集

复用现有 Axios 请求/响应拦截器，不改变 API 调用方：

- 只匹配 orders、menu/dish、members、marketing 业务域。
- request start 生成本地 `request_id`，只放入 Axios `config.meta`，不写入请求头或请求体。
- request end 使用 `performance.now()` 计算耗时。
- 状态区分：`success`、`business_error`、`http_error`、`network_error`、`timeout`、`cancelled`、`duplicate_skipped`。
- `payload_size` 优先读取响应 `Content-Length`；不可获得时记录 `null` 和 `size_source=unavailable`，禁止用高成本序列化伪造精确字节数。
- endpoint 与 request name 必须归一化动态 ID，不记录查询参数、请求正文、响应正文、手机号、会员姓名、订单明细或 token。

### 2.5 环境与版本

- `development` 映射为 `local`。
- `staging` 映射为 `staging`。
- `production` 映射为 `production`。
- 构建版本从实际 checkout 的 `git rev-parse HEAD` 注入；显式构建变量可以覆盖，但不得优先使用可能与指定 Release SHA 不同的 workflow `GITHUB_SHA`。
- 每条事件必须包含 environment 与完整 commit SHA，无法识别时明确记录 `unknown`，不得沿用旧版本值。

## 3. 统一事件字段

| 字段 | 规则 |
| --- | --- |
| `event_name` | 必填，使用本阶段五个受控事件名之一 |
| `timestamp` | 必填，事件生成时的墙上时钟时间 |
| `route` | 必填，归一化路由路径，不包含查询参数 |
| `page` | 必填，受控页面名；非目标页面 API 可为 `unknown` |
| `request_name` | API 事件必填；页面事件为 `null` |
| `request_id` | API 事件必填，本地关联使用，不发送给服务端 |
| `duration` | 完成事件必填；瞬时 start/enter 事件为 `null` |
| `status` | 必填，受控状态枚举 |
| `payload_size` | API end 字段；不可获得时为 `null` |
| `environment` | 必填：`local`、`staging`、`production` 或 `unknown` |
| `version` | 必填，实际构建 commit SHA 或 `unknown` |

允许增加不含隐私的关联字段，如 `visit_id`、`api_group`、`size_source`、`data_count`，但不得改变上述核心字段含义。

## 4. 数据流

```text
router before/after
        |
        v
page visit context ---- page explicit marker
        |                       |
        +-----------+-----------+
                    v
          unified event recorder <---- Axios interceptors
                    |
          +---------+---------+
          |                   |
          v                   v
 bounded memory queue   dev console/subscribers

          no network output
```

## 5. 错误与隔离规则

- 性能采集函数必须捕获自身错误并返回失败结果，不允许改变原 Promise 的 resolve/reject 行为。
- Axios 原有去重、鉴权清理、403 提示、raw response 和 ID 兼容逻辑必须保持。
- 业务接口失败仍由现有页面处理；采集层只记录，不弹提示、不重试、不改状态。
- 页面卸载后的迟到请求可以记录 API end，但不得被绑定到新的页面访问。
- 事件队列达到上限时只淘汰最旧事件，不允许无限增长。

## 6. TDD 测试设计

1. 事件结构：验证核心字段完整、环境/版本存在、非法输入安全降级。
2. 队列与订阅：验证 200 条上限、先进先出淘汰、订阅与取消订阅。
3. 页面采集：验证四个目标路由会生成 enter，首次内容和 ready 每次访问各一次。
4. API 成功：验证核心 API 产生 start/end、正数耗时、success 和可用的 payload size 来源。
5. API 失败：验证 business、HTTP、network、timeout、cancelled 与 duplicate skipped 可区分。
6. 接线检查：验证 router、request 和四个真实页面均连接统一采集入口，且源码中不存在性能网络发送。
7. 回归：运行新增测试、完整 `npm run check` 和 production build。

## 7. 预期文件范围

计划新增：

- `admin-h5/src/utils/adminPerformance.js`
- `admin-h5/scripts/test-performance-observability.mjs`
- `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE02_IMPLEMENTATION.md`

计划修改：

- `admin-h5/src/router/index.js`
- `admin-h5/src/api/request.js`
- `admin-h5/src/views/Dashboard.vue`
- `admin-h5/src/views/OrderManage.vue`
- `admin-h5/src/views/MenuManage.vue`
- `admin-h5/src/views/CustomerList.vue`
- `admin-h5/vite.config.js`
- `admin-h5/package.json`

不修改 `saas-base`、数据库、API 路径/字段、业务组件结构和生产部署脚本。

## 8. 实施结果

本节在完成 TDD 实施与真实命令验证后填写，不提前记录通过数或性能数据。

## 9. 当前限制

- 事件只存在于当前页面进程内，刷新或关闭后丢失。
- 没有生产持久化、跨会话查询、趋势分析、商家维度分析或告警。
- 本阶段只验证模型和采集边界，不能据此宣称任何性能瓶颈或优化结果。

## 10. 下一阶段原则

Phase 03 只能基于真实采集样本决定是否需要持久化以及是否调查 bundle、API、大列表或组件渲染；不得在没有样本前指定优化方向。
