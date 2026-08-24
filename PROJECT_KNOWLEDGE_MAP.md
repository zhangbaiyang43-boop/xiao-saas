# PROJECT_KNOWLEDGE_MAP

```
MODE=AUDIT_DRAFT
DATE=2026-08-24
CODE_CHANGE=NO
```

第一阶段扫描结果。不整理、不重写已有规范，只标明「有什么、算哪一类、谁说了算」。

---

## 当前知识库目录树

### A. Git 仓库（可随代码分发）

```
xiao/
├── AI_ENTRYPOINT.md                 ← 本阶段：AI 固定入口
├── PROJECT_INDEX.md                 ← 本阶段：知识索引
├── PROJECT_KNOWLEDGE_MAP.md         ← 本文件
├── AI_MEMORY_UPDATE_PROTOCOL.md
├── AI_COMPLETION_PROTOCOL.md
├── Claude.md / CLAUDE.md            项目总纲·工程操作（git/部署）
├── PRODUCT_RULES.md                 产品硬约束（点餐确认/支付）
├── docs/
│   ├── marketing/
│   │   └── MARKETING_AUTOMATION_COUPON_BACKEND_AUDIT.md 自动发券能力审计
│   ├── frontend/
│   │   ├── ADMIN_FRONTEND_CONSTITUTION.md 商家后台前端治理合同（Must）
│   │   ├── ADMIN_FRONTEND_DESIGN_AUDIT.md 商家后台前端设计审计（只读）
│   │   ├── ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md 商家后台高频页面治理符合度审计（只读）
│   │   ├── ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md 商家后台前端系统 Phase-01 审计与蓝图（只读）
│   │   ├── ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md 商家后台前端系统 Phase-02 最小可执行规则（Must，扩展 Constitution）
│   │   ├── ADMIN_FRONTEND_SYSTEM_PHASE03A_ORDER_STATE_MIGRATION.md OrderManage 状态真实性 Touch And Migrate（只读，验收证据）
│   │   ├── ADMIN_FRONTEND_SYSTEM_PHASE03B_DASHBOARD_MIGRATION.md Dashboard 经营视图 Touch And Migrate（只读，验收证据）
│   │   ├── ADMIN_FRONTEND_SYSTEM_PHASE03C_DISH_STATE_MIGRATION.md 菜品管理（MenuManage.vue）状态真实性 Touch And Migrate（只读，验收证据）
│   │   ├── DESIGN_SYSTEM_CURRENT.md 前端视觉现状审计
│   │   ├── HIGH_FREQUENCY_UI_AUDIT.md 顾客端高频路径视觉审计（只读）
│   │   ├── HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md CTA/CartBar 决策（OPEN）
│   │   ├── MASK_MIGRATION_AUDIT.md legacy .mask 迁移审计（只读）
│   │   ├── PAYMENT_SUCCESS_OVERLAY_DECISION.md 支付成功 overlay 产品合同
│   │   ├── CARTBAR_VISUAL_CONTRACT.md CartBar 视觉合同（只读）
│   │   ├── HIGH_FREQUENCY_ADOPTION_PHASE03_AUDIT.md 高频采用审计 PHASE-03
│   │   ├── MINI_UX_POLISH_AUDIT.md 顾客端上线前 UX 审计
│   │   ├── P1_MEMBER_EMPTY_STATE_AUDIT.md 会员空状态审计
│   │   ├── MENU_PERFORMANCE_AUDIT.md 菜单首屏性能审计（只读）
│   │   ├── MENU_PERFORMANCE_PHASE03_MEASURE.md 菜单首屏 PHASE-03 度量（只读）
│   │   └── MENU_PERFORMANCE_PHASE04_VERIFY.md 菜单首屏 PHASE-04 生产验证（meta 未取到）
│   ├── engineering/
│   │   ├── HOTFIX-LEDGER.md         小程序 hotfix 账本
│   │   └── release-process/         发布架构与 SOP（5 篇）
│   └── production-deployment.md
├── member-mini-client/docs/frontend/
│   └── FRONTEND_CONSTITUTION.md     小程序前端结构合同（CI 可执行）
├── member-mini-client/小程序运行说明.md
├── admin-h5/ENCODING.md
├── saas-base/
│   ├── MIGRATIONS.md                数据库迁移合同
│   ├── RUNNING.md
│   ├── PERFORMANCE.md
│   └── docs/                        员工权限 / 支付验收 / 推荐验收
└── .github/workflows/               三端 CI 门禁
```

仓库根没有 `README` / `CONTRIBUTING` / `AGENTS.md`。AI 工具目前主要靠 `Claude.md`。

未纳入知识库（不要当规范读）：`_final_gate_worktrees/`、`_final_release_worktrees/`、`saas-base.backup.*`、`node_modules/`、`dist/`。

### B. 本机 Obsidian（不在 git，本机 AI 必须当证据源）

Vault：`C:\Users\15936\Documents\Obsidian Vault`  
开心点单知识库：`开心点单_AI知识库\`

```
开心点单_AI知识库/
├── 00_项目总纲/项目总纲.md
├── 01_业务设计/业务设计.md
├── 01_产品规则/
│   ├── 产品规则.md
│   └── 产品操作系统/          哲学参考，非强约束
├── 02_技术架构/
│   ├── 技术架构.md
│   └── 业务与代码地图.md
├── 03_工程规范/工程规范.md
├── 03_AI协作/AI协作规则.md     已迁移，只作跳转
├── 04_前端规范/前端规范.md
├── 04_BUG记录/BUG记录.md       已迁入 10_，勿再写入
├── 05_后端规范/后端规范.md
├── 05_产品决策/产品决策记录.md  ADR 日志
├── 06_数据库规范/数据库规范.md
├── 06_开发日志/开发日志.md
├── 07_API规范/API规范.md
├── 07_产品操作系统/已迁移.md
├── 08_安全规范/安全规范.md
├── 09_AI协作规范/AI协作规范.md
├── 10_BUG案例库/BUG案例库.md
├── 11_开发流程/开发流程.md
└── 12_部署运维/部署运维.md
```

同 vault 还有 Codex 跨项目记忆 `00_Codex_Permanent_Memory/`（偏好、每日流水、项目页）。它不是开心点单规范正文，任务需要时读项目页，不要把它当成 Constitution。

---

## 每个目录作用

| 位置 | 作用 |
|---|---|
| 仓库根 `Claude.md` | AI 高频操作：commit/push 授权、生产路径、venv、`.env` |
| 仓库根 `PRODUCT_RULES.md` | 点餐确认/支付十条，改下单 UI 前必读 |
| `member-mini-client/docs/frontend/` | 可执行前端合同（Overlay/BaseSheet/CI） |
| `docs/frontend/ADMIN_FRONTEND_CONSTITUTION.md` | 商家后台新增与触摸变更的前端准入合同 |
| `docs/frontend/` | 设计系统现状审计 |
| `docs/engineering/` | 发布与 hotfix 证据 |
| `saas-base/docs` + `MIGRATIONS.md` | 后端专项合同 |
| Obsidian `00–12` | 给人看的结构化规范与案例；与仓库冲突时仓库优先 |
| Obsidian `产品操作系统/` | 产品哲学素材，现阶段不作为 Must |

---

## 权威文件列表

| 主题 | 权威文件 | 副本/展开 |
|---|---|---|
| Git / 生产部署命令 | `Claude.md` | Obsidian `12_部署运维` 只写判断，不覆盖命令 |
| 点餐确认与支付产品 | `PRODUCT_RULES.md` | Obsidian `01_产品规则` |
| 小程序 Overlay / primitive / touch-and-migrate | `FRONTEND_CONSTITUTION.md` | Obsidian `04_前端规范` 管拆分约定，不替代 Constitution |
| 商家后台前端治理 / touch-and-migrate | `docs/frontend/ADMIN_FRONTEND_CONSTITUTION.md` + `ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md` | `ADMIN_FRONTEND_DESIGN_AUDIT.md`、`ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md`、`ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md` 提供现状证据，不替代 Constitution |
| 视觉现状 | `docs/frontend/DESIGN_SYSTEM_CURRENT.md` | 无第二权威 |
| 数据库迁移 | `saas-base/MIGRATIONS.md` | Obsidian `06_数据库规范` |
| 租户隔离 | `saas-base/tests/test_tenant_isolation_scan.py` + Obsidian 工程规范 | |
| ADR | Obsidian `05_产品决策/产品决策记录.md` | 部分交互 ADR 正文在 `产品规则.md` |
| BUG | Obsidian `10_BUG案例库/BUG案例库.md` | 仓库 `HOTFIX-LEDGER.md` 补小程序专项 |
| 当前阶段叙事 | Obsidian `00_项目总纲` + `06_开发日志` | git log 是更硬的时间线 |

---

## 分类

### 项目总纲

- Obsidian `00_项目总纲/项目总纲.md`
- `Claude.md`（工程总纲）
- Codex `Projects/xiao-小程序全栈.md`

### 架构规则

- Obsidian `02_技术架构/技术架构.md`
- Obsidian `02_技术架构/业务与代码地图.md`
- Obsidian `03_工程规范/工程规范.md`

### 前端规则

- `member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md`（结构 / Overlay，Must）
- `docs/frontend/ADMIN_FRONTEND_CONSTITUTION.md`（商家后台准入合同，Must）
- `docs/frontend/ADMIN_FRONTEND_DESIGN_AUDIT.md`（商家后台治理依据，只读）
- `docs/frontend/ADMIN_HIGH_FREQUENCY_PAGE_AUDIT.md`（商家后台高频页面符合度审计，只读）
- `docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE01_AUDIT.md`（商家后台前端系统 Phase-01 审计与蓝图，只读）
- `docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE02_RULES.md`（商家后台前端系统 Phase-02 最小可执行规则，Must，扩展 Constitution）
- `docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03A_ORDER_STATE_MIGRATION.md`（OrderManage 状态真实性 Touch And Migrate，只读，验收证据）
- `docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03B_DASHBOARD_MIGRATION.md`（Dashboard 经营视图 Touch And Migrate，只读，验收证据）
- `docs/frontend/ADMIN_FRONTEND_SYSTEM_PHASE03C_DISH_STATE_MIGRATION.md`（菜品管理 MenuManage.vue 状态真实性 Touch And Migrate，只读，验收证据）
- `docs/frontend/DESIGN_SYSTEM_CURRENT.md`（视觉现状）
- `docs/frontend/MENU_PERFORMANCE_AUDIT.md`（菜单首屏性能，只读）
- Obsidian `04_前端规范/前端规范.md`（拆分与端侧约定）
- `member-mini-client/scripts/check-ui-contracts.mjs`（机器门禁）

### 后端规则

- Obsidian `05_后端规范/后端规范.md`
- Obsidian `07_API规范/API规范.md`
- Obsidian `08_安全规范/安全规范.md`
- `saas-base/docs/*`

### 数据库规则

- `saas-base/MIGRATIONS.md`
- Obsidian `06_数据库规范/数据库规范.md`

### 业务规则

- `PRODUCT_RULES.md`
- Obsidian `01_产品规则/产品规则.md`
- Obsidian `01_业务设计/业务设计.md`

### BUG 历史

- Obsidian `10_BUG案例库/BUG案例库.md`
- `docs/engineering/HOTFIX-LEDGER.md`

### 决策记录

- Obsidian `05_产品决策/产品决策记录.md`

### 开发日志 / 阶段

- Obsidian `06_开发日志/开发日志.md`
- Obsidian `11_开发流程/开发流程.md`

---

## 扫描结论（给后续阶段用）

1. 规范已经够多。缺的是仓库内固定入口，不是再写一套规范。
2. 真正给 AI 自动加载的只有 `Claude.md`。Frontend Constitution、PRODUCT_RULES、Obsidian 知识库以前没有统一入口。
3. Obsidian 是主知识库，但 **不在 git**。入口协议必须同时给出本机路径和「无 vault 时的仓库回退」。
4. Frontend Constitution 与 Obsidian 前端规范互补：前者是弹层/primitive/CI 合同，后者是拆分习惯。前端任务两份都要能被引导到，且 Constitution 不可跳过。
