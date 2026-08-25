# Admin 前端安全整改 — CustomerList 会话上下文凭证泄露修复（Phase-06-SEC）

```text
PHASE=P0-ADMIN-FRONTEND-SYSTEM-PHASE-06-SEC
STATUS=CUSTOMER_LIST_CONTEXT_CREDENTIAL_REMEDIATION
DIRECTION=方向一（identity 只用 tenant_id，登出时显式清理）
BUSINESS_CODE_CHANGED=YES（admin-h5，仅 2 个源文件）
```

## 0. 背景

[Phase-06 审计](./ADMIN_FRONTEND_SYSTEM_PHASE06_NEXT_PRIORITY_AUDIT.md)在体验优先级排序之前的强制 `SECURITY_PREFLIGHT` 阶段发现：Phase-05C 为 `CustomerList.vue` 引入的会话上下文保持机制，把原始 Bearer Token 明文拼进 `identity` 字段后写入了 `sessionStorage`——即凭证的第二份明文持久化副本。该阶段按规则中止（`RESULT B: BLOCKED_BY_CREDENTIAL_PERSISTENCE`），只定义了两个候选修复方向，未选择、未实施。

本阶段用户已选定**方向一**：`identity` 只用 `tenant_id`（去掉 token），并在 `stores/auth.js` 的 `clearAuth()` 里显式清理这个 key。本阶段负责实施、TDD 验证、回归、报告。

## 1. Baseline

```text
BASELINE_SHA = b3a4cb4f0bea862d1dc2d2fcc97d50a7cb1589d8
BRANCH = main
WORKTREE_DIRTY = YES（与本阶段无关）
UNRELATED_WIP =
  M  saas-base/tests/test_performance_staging_environment_contracts.py
  M  scripts/performance-staging.ps1
  ?? docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE0*.md（多个，另一条工作线）
  ?? docs/superpowers/plans/2026-08-24-admin-performance-observability-phase03c.md
```

以上 WIP 全程未删除、未 reset、未 clean、未 stash、未混入本阶段提交。

## 2. 真实 RED 验证（修复前，针对当前 HEAD 的真实源码）

写了新的合同测试 `admin-h5/scripts/test-phase06sec-customer-context-credential-hardening.mjs`，在**未做任何代码修改前**对 commit `b3a4cb4` 的真实源码运行：

```text
FAIL 0. currentContextIdentity() no longer reads or embeds the raw token
FAIL 2. clearAuth() in stores/auth.js explicitly purges the saved customer-list context
FAIL 5. No other place in CustomerList.vue reads the token for any storage-bound purpose
Phase-06-SEC RED failures: 3
```

（另外 2 项——payload 不含 token 字面量的纯 mirror 测试、tenant 隔离的纯 mirror 测试——在这一步就已经 PASS，因为它们只验证目标行为本身的逻辑，不依赖当前源码是否已修复；3 项 FAIL 精确对应本阶段要修的 3 处。）这 3 处 FAIL 证实：修复前，`currentContextIdentity()` 确实读取原始 token，`clearAuth()` 确实没有清理这个 key。

## 3. 修复实施

### 3.1 `admin-h5/src/views/CustomerList.vue`

`currentContextIdentity()`：

```diff
- function currentContextIdentity() {
-   return `${localStorage.getItem('tenant_id') || ''}:${localStorage.getItem('token') || ''}`
- }
+ function currentContextIdentity() {
+   return localStorage.getItem('tenant_id') || ''
+ }
```

`token` 从这个函数、以及整个文件里对 sessionStorage 相关代码路径中彻底移除（`grep "localStorage.getItem('token')"` 在 `CustomerList.vue` 内确认为 0 处匹配）。`saveListContext()`/`consumeSavedListContext()`/`restoreListContext()` 三个函数体本身未改一行——它们只是调用 `currentContextIdentity()`，行为随之自动收紧，不需要跟着改。

### 3.2 `admin-h5/src/stores/auth.js`

`clearAuth()` 尾部新增一行：

```diff
    clearSession()
    clearDeviceCredential()
    ;['role', 'permissions', 'home_path', 'account_id', 'account_name', 'account_username', 'auth_method'].forEach((k) => {
      localStorage.removeItem(k)
    })
+   sessionStorage.removeItem('admin_customer_list_context')
  }
```

`clearAuth()` 是这个仓库里唯一真正执行登出清理的函数（`grep "clearAuth\|logoutCurrentDevice"` 确认：`More.vue`、`FrontdeskWorkbench.vue`、`KitchenWorkbench.vue`、`WaiterWorkbench.vue` 四处登出入口全部经过 `logoutCurrentDevice()` → `clearAuth()`，或 `More.vue` 里的兜底直接调用 `clearAuth()`），加这一行覆盖了全部真实登出路径，不需要在四个页面分别处理。

未新建共享常量模块存放 `'admin_customer_list_context'` 这个 key 字符串——两处各自内联字面量，符合仓库既有的"不为一个字符串引入新抽象"的风格；`clearAuth()` 处加了注释说明这个 key 从哪来、为什么现在需要显式清理。

## 4. 真实 GREEN 验证

```text
PASS 0. currentContextIdentity() no longer reads or embeds the raw token
PASS 1. saveListContext() payload can never contain the literal token value
PASS 2. clearAuth() in stores/auth.js explicitly purges the saved customer-list context
PASS 3. clearAuth() cleanup mirror actually removes a previously saved context
PASS 4. Tenant isolation is still enforced without the token
PASS 5. No other place in CustomerList.vue reads the token for any storage-bound purpose
Phase-06-SEC customer context credential hardening: passed
```

## 5. 对 Phase-05C 既有测试的必要同步

方向一是一次真实的行为变化，不只是内部实现细节：Phase-05C 的 `test-phase05c-customer-context-preservation.mjs` 有两处直接依赖旧 identity 公式，按理必须同步，而不是被动破坏后放着不管：

- **Test 0**（mirror 逐字匹配源码）：`currentContextIdentity` 的 pin 字符串从 `` `${tenant_id}:${token}` `` 改成 `tenant_id` 单值，随源码同步更新。
- **Test 6**：原断言是"登出（token 轮换）会让同租户下的旧上下文失效"，其失效机制曾经是"identity 里的 token 变了所以不匹配"——这个机制被本阶段刻意移除了。重写后的 Test 6 明确断言新的契约：**同租户内单纯的 token 轮换、不经过 `clearAuth()`，不再会使旧上下文失效**（这是方向一的设计后果，不是遗漏）；真正的登出失效改由 Test 2/3（本阶段新测试）断言 `clearAuth()` 显式清理这个 key。新 Test 6 的注释里指向了具体的替代验证点，避免未来有人碰这块代码时误以为"token 轮换会自动失效"这条旧假设仍然成立。

两处修改后，Phase-05C 全部 11 项 + 新增架构检查项，`test-phase05c-customer-context-preservation.mjs` 重跑全部 PASS。

## 6. 回归

```bash
npm run check
```

包含全部既有套件（`workbench-sync`、`p0-08-sync/acceptance`、`dashboard-actionable-state`、`phase03a~e`、`phase04`、`phase05a~c`）+ 本阶段新增的 `test:phase06sec-customer-context-credential-hardening`，最后跑 `vite build`。结果：**91 PASS / 0 FAIL**，`vite build` 成功产出 `dist/`（含 chunk 体积警告，属既有基线状态，非本阶段引入）。

## 7. 影响面确认

```text
CHANGED_FILES=
  admin-h5/src/views/CustomerList.vue（currentContextIdentity 收紧）
  admin-h5/src/stores/auth.js（clearAuth 新增一行显式清理）
  admin-h5/scripts/test-phase05c-customer-context-preservation.mjs（同步 2 处 pin/断言）
  admin-h5/scripts/test-phase06sec-customer-context-credential-hardening.mjs（新增，本阶段合同测试）
  admin-h5/package.json（新增 test 脚本，接入 check 链）
  docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE06_SEC_CUSTOMER_CONTEXT_CREDENTIAL_REMEDIATION.md（新增，本文件）
  PROJECT_INDEX.md / PROJECT_KNOWLEDGE_MAP.md（索引更新）
UNRELATED_WIP_INCLUDED=NO
```

`stores/auth.js` 是登录状态的共享文件，但改动本身只新增一行、只影响登出清理路径，四个真实登出入口（More.vue + 三个 Workbench）都经过统一的 `clearAuth()`，无需分别改动或分别测试；`npm run check` 里已有的 `test:workbench-sync`/`test:staff-device-cookie` 等既有套件未受影响（全部 PASS），说明这一行改动没有触及登录态其余部分。

`saas-base`、`member-mini-client` 均未涉及，无需部署改动。`admin-h5` 是静态 SPA，需要重新构建部署（`npm run build` 已在 `check` 链里验证通过；实际发布仍走独立的 admin-h5 部署路径，本报告不代为执行）。

## 8. 是否彻底解决

`sessionStorage['admin_customer_list_context']` 现在只包含 `{identity: tenant_id, keyword, page}`，`tenant_id` 本身不是敏感凭证（不能用来通过后端鉴权，只是租户维度的公开标识符），登出会显式清空这个 key。原始 Bearer Token 除 `localStorage['token']`（`utils/session.js` 管理的唯一权威位置）外不再有任何持久化副本——`grep -rn "localStorage.getItem('token')" admin-h5/src` 确认全仓库仅 `api/request.js`（鉴权 header 拼接）、`utils/session.js`（`getToken()`/`getSession()`/`hasValidSession()`）几处读取，均为原有的、非持久化到别处的正常用法。

```text
FINAL_DECISION=RESULT A: CREDENTIAL_PERSISTENCE_REMEDIATED
```

## NEXT_PHASE

安全整改到此完成。Phase-06 的信息层级/响应式/视觉系统/可用性四选一体验优先级审计（`PART_01~PART_20`）此前完全没有开始，现在可以在这个已修复的基础上重新执行——按 Phase-06 报告原有的 `NEXT_PHASE` 指引，重新从头做完整审计，不能假设旧报告里不存在的结论。
