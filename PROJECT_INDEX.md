# 项目知识索引

只做索引，不复制正文。AI 从 [AI_ENTRYPOINT.md](./AI_ENTRYPOINT.md) 进来后，用本文件找证据。

仓库根：`C:\Users\15936\Desktop\xiao`  
Obsidian 知识库（本机，不在 git）：`C:\Users\15936\Documents\Obsidian Vault\开心点单_AI知识库`  
分类说明见 [PROJECT_KNOWLEDGE_MAP.md](./PROJECT_KNOWLEDGE_MAP.md)

冲突时：**仓库文件 > Obsidian 副本**。

---

## 项目背景

- 本机总纲：`C:\Users\15936\Documents\Obsidian Vault\开心点单_AI知识库\00_项目总纲\项目总纲.md`
- 本机业务设计：`...\01_业务设计\业务设计.md`
- 本机业务与代码地图：`...\02_技术架构\业务与代码地图.md`
- Codex 项目页：`C:\Users\15936\Documents\Obsidian Vault\00_Codex_Permanent_Memory\Projects\xiao-小程序全栈.md`

## 产品规则

- 仓库硬约束：[PRODUCT_RULES.md](./PRODUCT_RULES.md)
- 本机展开：`...\01_产品规则\产品规则.md`
- 本机产品操作系统（参考，非强约束）：`...\01_产品规则\产品操作系统\`

## 技术架构

- 本机：`...\02_技术架构\技术架构.md`
- 本机工程红线：`...\03_工程规范\工程规范.md`
- 后端运行：`saas-base/RUNNING.md`
- 性能备忘：`saas-base/PERFORMANCE.md`

## 前端规则

- **顾客端结构合同（必须）**：[member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md](./member-mini-client/docs/frontend/FRONTEND_CONSTITUTION.md)
- 视觉现状审计（只读，不是新规范）：[docs/frontend/DESIGN_SYSTEM_CURRENT.md](./docs/frontend/DESIGN_SYSTEM_CURRENT.md)
- 设计系统采用审计：[docs/frontend/DESIGN_SYSTEM_ADOPTION_AUDIT.md](./docs/frontend/DESIGN_SYSTEM_ADOPTION_AUDIT.md)
- 小程序功能可见性审计：[docs/frontend/MINI_FEATURE_VISIBILITY_AUDIT.md](./docs/frontend/MINI_FEATURE_VISIBILITY_AUDIT.md)
- 小程序订单入口审计：[docs/frontend/ORDER_ENTRY_AUDIT.md](./docs/frontend/ORDER_ENTRY_AUDIT.md)
- 顾客端高频路径视觉审计（首页/菜单/购物车/结算/支付成功，只读）：[docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md](./docs/frontend/HIGH_FREQUENCY_UI_AUDIT.md)
- 高频路径 CTA / CartBar 设计决策（OPEN，未实现）：[docs/frontend/HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md](./docs/frontend/HIGH_FREQUENCY_CTA_CARTBAR_DECISION.md)
- legacy `.mask` 迁移审计（Checkout/Spec/Coupon/Success/Welcome，只读）：[docs/frontend/MASK_MIGRATION_AUDIT.md](./docs/frontend/MASK_MIGRATION_AUDIT.md)
- 支付成功 overlay 产品合同（已冻结）：[docs/frontend/PAYMENT_SUCCESS_OVERLAY_DECISION.md](./docs/frontend/PAYMENT_SUCCESS_OVERLAY_DECISION.md)
- CartBar 视觉合同（只读审计）：[docs/frontend/CARTBAR_VISUAL_CONTRACT.md](./docs/frontend/CARTBAR_VISUAL_CONTRACT.md)
- 高频路径采用审计 PHASE-03（PriceText / 金额层级 / layer）：[docs/frontend/HIGH_FREQUENCY_ADOPTION_PHASE03_AUDIT.md](./docs/frontend/HIGH_FREQUENCY_ADOPTION_PHASE03_AUDIT.md)
- 顾客端上线前 UX 体验审计：[docs/frontend/MINI_UX_POLISH_AUDIT.md](./docs/frontend/MINI_UX_POLISH_AUDIT.md)
- 会员/空状态体验审计：[docs/frontend/P1_MEMBER_EMPTY_STATE_AUDIT.md](./docs/frontend/P1_MEMBER_EMPTY_STATE_AUDIT.md)
- 小程序菜单首屏性能审计（只读）：[docs/frontend/MENU_PERFORMANCE_AUDIT.md](./docs/frontend/MENU_PERFORMANCE_AUDIT.md)
- 菜单首屏 PHASE-03 度量（只读）：[docs/frontend/MENU_PERFORMANCE_PHASE03_MEASURE.md](./docs/frontend/MENU_PERFORMANCE_PHASE03_MEASURE.md)
- 营销自动化发券后端审计：[docs/marketing/MARKETING_AUTOMATION_COUPON_BACKEND_AUDIT.md](./docs/marketing/MARKETING_AUTOMATION_COUPON_BACKEND_AUDIT.md)
- 本机前端约定：`...\04_前端规范\前端规范.md`
- 小程序样式 token：`member-mini-client/src/styles/global.scss`
- 商家样式 token：`admin-h5/src/styles/global.scss`
- 前端 UI 合同扫描：`member-mini-client/scripts/check-ui-contracts.mjs`

## 后端规则

- 本机：`...\05_后端规范\后端规范.md`
- 本机 API：`...\07_API规范\API规范.md`
- 本机安全：`...\08_安全规范\安全规范.md`
- 员工权限：`saas-base/docs/merchant-staff-permissions.md`
- 支付模式验收：`saas-base/docs/payment_mode_manual_acceptance.md`

## 数据库规则

- 仓库迁移合同：[saas-base/MIGRATIONS.md](./saas-base/MIGRATIONS.md)
- 本机模型/租户字段：`...\06_数据库规范\数据库规范.md`
- 隔离扫描：`saas-base/tests/test_tenant_isolation_scan.py`

## BUG 案例

- 本机主库：`...\10_BUG案例库\BUG案例库.md`
- 仓库 hotfix 账本：[docs/engineering/HOTFIX-LEDGER.md](./docs/engineering/HOTFIX-LEDGER.md)
- 旧入口（已迁移，勿写入）：`...\04_BUG记录\BUG记录.md`

## ADR 决策

- 本机：`...\05_产品决策\产品决策记录.md`
- 点餐确认十条同时写在 [PRODUCT_RULES.md](./PRODUCT_RULES.md)

## 当前开发阶段

- 本机总纲「当前阶段」节：`...\00_项目总纲\项目总纲.md`
- 本机开发日志：`...\06_开发日志\开发日志.md`
- 本机开发流程：`...\11_开发流程\开发流程.md`

## Git / 部署 / 生产

- 仓库操作红线：[Claude.md](./Claude.md)
- 发布知识库：[docs/engineering/release-process/](./docs/engineering/release-process/)
- 发布总述：[docs/production-deployment.md](./docs/production-deployment.md)
- 本机判断层：`...\12_部署运维\部署运维.md`

## AI 治理（本阶段新增）

- 入口：[AI_ENTRYPOINT.md](./AI_ENTRYPOINT.md)
- 知识更新：[AI_MEMORY_UPDATE_PROTOCOL.md](./AI_MEMORY_UPDATE_PROTOCOL.md)
- 任务收尾：[AI_COMPLETION_PROTOCOL.md](./AI_COMPLETION_PROTOCOL.md)
- 本机协作规范：`...\09_AI协作规范\AI协作规范.md`

## CI 门禁（命令证据，不是说明文）

- 后端：`.github/workflows/saas-base-ci.yml`、`backend-candidate-certification.yml`、`backend-full.yml`
- 小程序：`.github/workflows/member-mini-client-ci.yml`
- 商家后台：`.github/workflows/admin-h5-ci.yml`、`admin-h5-release.yml`
