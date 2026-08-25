# Admin 前端下一优先级审计 — 在 Security Preflight 阶段中止（Phase-06）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-06
STATUS=ADMIN_EXPERIENCE_NEXT_PRIORITY_AUDIT
MODE=AUDIT_AND_PRIORITY_FREEZE_ONLY
PHASE_TYPE=CROSS_SYSTEM_EXPERIENCE_GAP_AUDIT
RUN_MODE=AUDIT_ONLY
BUSINESS_CODE_CHANGED=NO
```

## 0. Baseline

```text
BASELINE_SHA = 5c66d799a8381c7ad9dbf918d9772af020522001
BRANCH = main
WORKTREE_DIRTY = YES（与本阶段无关）
UNRELATED_WIP =
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条工作线）
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 全程未删除、未 reset、未 clean、未 stash、未混入本阶段提交。

## 1. Security Preflight（在此中止）

按本阶段的强制前置要求，进入体验优先级审计前先只读复核了 Phase-05C 新增的 `CustomerList.vue` 会话上下文持久化机制（当前 HEAD，非历史报告结论）。

### 核实过程

`admin-h5/src/views/CustomerList.vue`（当前）：

```js
function currentContextIdentity() {
  return `${localStorage.getItem('tenant_id') || ''}:${localStorage.getItem('token') || ''}`
}

function saveListContext() {
  try {
    sessionStorage.setItem(CUSTOMER_LIST_CONTEXT_KEY, JSON.stringify({
      identity: currentContextIdentity(),
      keyword: keyword.value,
      page: page.value,
    }))
  } catch { ... }
}
```

`identity` 字段是 `tenant_id` 和 `token` 拼接后的字符串，`token` 取自 `localStorage.getItem('token')`——追踪这个值的真实来源：

- `admin-h5/src/utils/session.js:18`：`saveSession()` 里 `localStorage.setItem(TOKEN_KEY, data.token)`，`TOKEN_KEY = 'token'`。
- `admin-h5/src/api/request.js:83-85`：每次请求都读 `localStorage.getItem('token')`，设置 `config.headers.Authorization = \`Bearer ${token}\``。

**这是商家账号登录后用于所有后端接口鉴权的真实 Bearer Token，不是脱敏 ID、不是会话指纹、不是派生值。** `saveListContext()` 把这个原始 token 完整拼进 `identity` 字符串，再 `JSON.stringify` 写进 `sessionStorage`——`identity` 字段的唯一用途是等值比较（第 05C 报告设计的租户隔离机制），但实现方式是把凭证本身的明文复制了一份到另一个存储位置。

### 结论

```text
SESSION_CONTEXT_STORAGE = sessionStorage，key: admin_customer_list_context
PERSISTED_FIELDS = { identity, keyword, page }；identity = `${tenant_id}:${token}`（token 为原始 Bearer Token 明文）
RAW_ACCESS_TOKEN_PERSISTED_IN_CONTEXT = YES
AUTH_CREDENTIAL_DUPLICATED = YES（token 本来只在 localStorage 一处由 utils/session.js 管理；Phase-05C 在 sessionStorage 里又写了一份明文副本）
```

```text
SECURITY_PREFLIGHT=FAIL
```

按规则，发现 `RAW_ACCESS_TOKEN_PERSISTED_IN_CONTEXT=YES` 时必须立即停止体验优先级审计，不在本阶段顺手修代码，单独提出最小安全整改 Phase。本报告到此为止不再执行 PART_01 ~ PART_20 的信息层级/响应式/视觉/可用性审计——那些工作没有意义在一个已知凭证泄露面尚未收敛的状态下进行。

**这是本次审计新发现的问题，不是外部引入的**：这个存储机制是 Phase-05C 本身设计并实现的（为了给 `CustomerList.vue` 的会员搜索/翻页上下文做租户隔离，复用了 `useWorkbenchSync.js` 里 `currentIdentity()` 的字符串拼接写法）。`useWorkbenchSync.js` 的原始用法把这个拼接字符串**只留在内存里**（闭包变量 `activeIdentity`，用于比较本次请求和上次请求是否跨了身份，从不写入任何持久化存储）；Phase-05C 复用了同一种"拼 identity 字符串"的思路，但把结果**写进了 sessionStorage**——这一步是这次新引入的风险，不是复制已有的安全模式。本阶段的审计流程正确地在体验优先级排序之前拦住了它。

## 2. 为什么在这里停止，而不是顺手修一行

- 本 Phase 明确是 `AUDIT_AND_PRIORITY_FREEZE_ONLY` / `DOCS_ONLY`，规则原文写明"不要在本 Phase 顺手修代码"。
- 修复方式本身需要一次真正的技术判断（是否要碰 `stores/auth.js`，第 3 节的两个候选方案取舍不同），不是一行改动可以草率决定的，应该作为独立、有自己审计和测试的 Phase 来做，而不是在体验优先级审计报告里顺带处理。
- 在真正解决凭证持久化问题之前，讨论"下一步该优化信息层级还是响应式"没有意义——两者不在同一个风险量级上。

## 3. 提议的最小安全整改 Phase（未实施，仅定义范围）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-06-SEC
STATUS=CUSTOMER_LIST_CONTEXT_CREDENTIAL_REMEDIATION
SCOPE=admin-h5/src/views/CustomerList.vue 的 currentContextIdentity()/saveListContext()/consumeSavedListContext()
```

问题定位：`CustomerList.vue` 第 156-186 行区域（`CUSTOMER_LIST_CONTEXT_KEY` 常量到 `consumeSavedListContext` 函数结束）。目标不变——仍然需要租户隔离（不能让 A 租户的搜索上下文出现在 B 租户）和登出失效（退出登录后不能恢复旧上下文），但**不能再用原始 token 明文做这件事**。

两个候选修复方向，留给该 Phase 自己评审取舍，本阶段不预先拍板：

**方向一：identity 只用 tenant_id，登出时显式清理**
- `currentContextIdentity()` 改为只返回 `localStorage.getItem('tenant_id') || ''`，不再拼接 token。
- 代价：同一租户内的"登出再登录"不会让 tenant_id 变化，单靠 tenant_id 无法让登出自动失效旧上下文，需要在 `stores/auth.js` 的 `clearAuth()`（第 91-104 行区域）里显式加一行 `sessionStorage.removeItem('admin_customer_list_context')`。
- 优点：sessionStorage 里彻底不再出现任何凭证或凭证衍生值；登出失效是显式、可读的一行代码，不依赖"token 变了所以间接失效"这种隐含推理。
- 代价：需要触碰 `stores/auth.js`（多个页面共用的登录状态文件），改动虽小但影响面是"全局登出流程"，需要相应的回归验证（覆盖 More.vue / FrontdeskWorkbench.vue / KitchenWorkbench.vue / WaiterWorkbench.vue 四处 `logoutCurrentDevice()` 调用点）。

**方向二：保留 token 参与 identity，但存之前先做非对称处理**
- `currentContextIdentity()` 里对 token 部分做一次不可逆的摘要（哪怕是简单的非加密哈希，只要不能从存储的值反推出原始 token），只把摘要拼进 identity。
- 优点：改动完全局限在 `CustomerList.vue` 一个文件，不碰 `stores/auth.js`；登出后 token 变化，摘要跟着变化，失效逻辑不需要改。
- 代价：需要引入一个哈希函数（哪怕是几行内联实现），比方向一多一点点复杂度；哲学上仍然是"存了一个凭证衍生值"，不如方向一彻底干净。

两个方向都能通过一份和 Phase-05C 类似的、真实的 RED→GREEN 合同测试验证（核心断言：`sessionStorage` 写入的值任何时候都不能整串包含 `localStorage.getItem('token')` 的原始返回值）。本阶段不实现，不选择,只把问题和候选方案定义清楚,留给专门的整改 Phase。

## ACCEPTANCE

1. **Phase-05C 是否存在 raw credential 额外持久化？** 是。`CustomerList.vue` 的 `saveListContext()` 把 `localStorage.getItem('token')` 的原始返回值拼进 `identity` 字符串后写入 `sessionStorage`，是本仓库里这个 Bearer Token 除 `localStorage['token']` 之外的第二份明文存储。
2-15. **不适用**——按 SECURITY_PREFLIGHT 规则，发现凭证持久化问题后必须立即停止体验优先级审计，本阶段未执行信息层级、响应式、视觉系统、可用性等审计（PART_01~PART_20），因此关于这些方向的成熟度、系统性判断、正反方评审等问题在本阶段没有真实工作支撑对应回答，如实标记为不适用，不编造答案。
16. **本阶段是否保持 Docs-Only？** 是。本阶段没有修改任何 `admin-h5` 业务代码、组件、样式、路由、API，也没有修改 `saas-base`/`member-mini-client`；仅新增本报告文件并更新索引。

```text
FINAL_DECISION=RESULT B: BLOCKED_BY_CREDENTIAL_PERSISTENCE
```

## COMMIT_RULE

```text
CHANGED_FILES=
  docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE06_NEXT_PRIORITY_AUDIT.md（新增，本文件）
  PROJECT_INDEX.md
  PROJECT_KNOWLEDGE_MAP.md
STAGED_FILES=同上，仅这 3 个文件
UNRELATED_WIP_INCLUDED=NO
```

## NEXT_PHASE

不进入 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-06A`（体验优先级实现阶段）。下一步应该是 `P0-ADMIN-FRONTEND-SYSTEM-PHASE-06-SEC`（第 3 节定义的最小安全整改），在这个问题解决并有真实测试锁定之后，才重新执行一次完整的 Phase-06 体验优先级审计——本报告的 PART_01~PART_20 工作完全没有开始，不能跳过安全整改直接假设"审计结论不变"。
