# AI 进入项目流程

```
PHASE=AI-PROJECT-GOVERNANCE-FOUNDATION-PHASE-01
AUDIENCE=Codex / Claude Code / Cursor / Grok / 其它接管本仓库的 AI
```

任何 AI 开始任务前必须先读本文件。不要凭训练记忆发明规范，不要重新整理已有文档。

本仓库的规范已经存在。本文件只解决一件事：**先读哪份证据**。

冲突时以仓库内文件为准，不以聊天记忆、不以 Obsidian 副本覆盖：

1. 支付 / 金额 / 订单确认 → `PRODUCT_RULES.md`
2. Git / 部署 / 生产操作 → `Claude.md`（即 `CLAUDE.md`）
3. 顾客端小程序 Overlay / 弹层 / primitive → `member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md`
4. 其它产品/工程细则 → Obsidian `开心点单_AI知识库`（本机可读；不在 git）

---

## Step 1 — 读索引

读取：

- [PROJECT_INDEX.md](./PROJECT_INDEX.md)

需要理解「现有知识分成几类、权威在哪」时，再读：

- [PROJECT_KNOWLEDGE_MAP.md](./PROJECT_KNOWLEDGE_MAP.md)

不要把索引正文复制进回复。按任务打开对应链接。

---

## Step 2 — 按任务类型定位规则

只读与当前任务相关的证据。不要整库通读。

### UI / 小程序前端 / 弹层 / 组件

必须读：

1. `member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md`
2. `docs/frontend/DESIGN_SYSTEM_CURRENT.md`（现状审计，不是新视觉规范）

本机再读：

3. `C:\Users\15936\Documents\Obsidian Vault\开心点单_AI知识库\04_前端规范\前端规范.md`

Constitution 里下列条款对前端改动全部有效，不得跳过：

- Authority hierarchy：支付合同 > Constitution > named primitives > legacy
- Primitive authority：Pages → Business Components → primitives → tokens
- Overlay contract：全屏遮罩归 BaseOverlay；新标准底栏归 BaseSheet
- `TOUCH_AND_MIGRATE=REQUIRED`
- `BIG_BANG_REWRITE=FORBIDDEN`
- `DOM_ORDER_IS_AUTHORITY=NO`

商家后台 UI 另读 `admin-h5/src/styles/global.scss` 与 Design System 文档中的商家端章节。不要把小程序弹层合同套到 Ant Design 页面上。

### 支付 / 下单 / 金额

必须读：

1. `PRODUCT_RULES.md`
2. 本机 `开心点单_AI知识库\01_产品规则\产品规则.md`
3. 本机 `开心点单_AI知识库\05_产品决策\产品决策记录.md`
4. 本机 `开心点单_AI知识库\10_BUG案例库\BUG案例库.md`（资金/支付相关条目）

代码证据优先：`saas-base/app/services/order_payment_service.py`、`order_lifecycle_service.py`、`member-mini-client/src/subpkg-order/composables/useCheckout.js`。

### 订单状态 / 历史订单 / 商家接单

必须读：

1. `PRODUCT_RULES.md`（若涉及确认/支付）
2. 本机 `开心点单_AI知识库\02_技术架构\业务与代码地图.md`
3. 本机 BUG 案例库中的订单条目

### 数据库 / 模型 / 迁移

必须读：

1. `saas-base/MIGRATIONS.md`
2. 本机 `开心点单_AI知识库\06_数据库规范\数据库规范.md`
3. 本机 `开心点单_AI知识库\03_工程规范\工程规范.md`（租户隔离）

正式环境只允许 Alembic。新业务表默认继承 `BaseModel`（含 `tenant_id`）。

### API / 鉴权 / 多租户

必须读：

1. 本机 `开心点单_AI知识库\07_API规范\API规范.md`
2. 本机 `开心点单_AI知识库\05_后端规范\后端规范.md`
3. 本机 `开心点单_AI知识库\08_安全规范\安全规范.md`
4. `saas-base/tests/test_tenant_isolation_scan.py`（隔离扫描合同）

### BUG / 回归 / 生产事故

必须读：

1. 本机 `开心点单_AI知识库\10_BUG案例库\BUG案例库.md`
2. `docs/engineering/HOTFIX-LEDGER.md`
3. 相关测试文件（不要只看文字记录）

### 架构 / 分层 / 拆分

必须读：

1. 本机 `开心点单_AI知识库\02_技术架构\技术架构.md`
2. 本机 `开心点单_AI知识库\03_工程规范\工程规范.md`
3. 前端任务同时读 Frontend Constitution

### 产品是否该做 / ADR

必须读：

1. `PRODUCT_RULES.md`
2. 本机 `开心点单_AI知识库\01_产品规则\产品规则.md`
3. 本机 `开心点单_AI知识库\05_产品决策\产品决策记录.md`

`01_产品规则/产品操作系统/` 是产品哲学参考，**不是**当前强约束。

### 部署 / 生产 / 发布

必须读：

1. `Claude.md`
2. `docs/engineering/release-process/`
3. 本机 `开心点单_AI知识库\12_部署运维\部署运维.md`（判断层；命令以 `Claude.md` 为准）

### 本机 Obsidian 读不到时

CI、其它机器、无 vault 权限：只使用本仓库 `PROJECT_INDEX.md` 里的 git 内链接。不要假装已经读过 Obsidian。

---

## Step 3 — 改代码前必须先输出

禁止直接改代码。先用简短条目写清：

- **当前适用规则**：准备遵守的文件路径（至少 Constitution / PRODUCT_RULES / Claude.md 中相关的那些）
- **历史约束**：BUG 案例、ADR、hotfix ledger 里会挡住方案的条目
- **影响范围**：`member-mini-client` / `saas-base` / `admin-h5` / `channel-h5` 哪些端，以及是否需要 migration / 小程序发版 / 后台静态发布
- **修改方案**：准备动哪些文件、不准备动哪些文件

用户在本任务里已经给出完整实施规格，且明确要求改代码时，仍要先输出以上四项，再动手。

---

## Step 4 — 结束时走完成协议

读取并遵守：

- [AI_COMPLETION_PROTOCOL.md](./AI_COMPLETION_PROTOCOL.md)
- [AI_MEMORY_UPDATE_PROTOCOL.md](./AI_MEMORY_UPDATE_PROTOCOL.md)

不是每次改动都更新知识库。文案、CSS 微调、单页视觉、普通重构不写 ADR、不写 BUG 案例。
