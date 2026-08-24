# AI Memory Update Protocol

不是所有代码修改都要记知识库。只在产生**长期约束**时更新。

权威仍是原文件。本协议只规定：**何时写、写到哪、写什么**。不要另开一套规范。

---

## 必须更新

### 1. P0 / P1 BUG 修复

写入本机：

`C:\Users\15936\Documents\Obsidian Vault\开心点单_AI知识库\10_BUG案例库\BUG案例库.md`

新记录放在「记录」节最上面。沿用该文件已有模板：

- 问题（现象）
- 根因
- 错误方案（若尝试过且失败，必须写；没试过就写「无」）
- 最终方案（修复）
- 影响范围（端 + 严重度）
- 测试结果 / 相关 commit

小程序专项 hotfix 若已有仓库账本格式，同时追加：

`docs/engineering/HOTFIX-LEDGER.md`

P2 体验问题默认不写；只有会再次误导后续 AI 时才记一条。

### 2. 架构变化

写入本机：

- `...\02_技术架构\技术架构.md` 和/或 `业务与代码地图.md`
- 决策本身另记 ADR（见第 4 条）

必须写清：为什么变化、影响模块、迁移方式（TOUCH_AND_MIGRATE / 是否需要兼容旧数据）。

禁止为了「架构变化」去大改 Frontend Constitution。Constitution 仍是独立合同；若 overlay/primitive 权威变了，在 ADR 里写，另开阶段改 Constitution，本协议不授权顺手改它。

### 3. 新增工程规则

写入对应**已有**规范文件，不要新建平行文档：

| 规则类型 | 写入 |
|---|---|
| Git / 生产操作 | 仓库 `Claude.md` |
| 点餐确认 / 支付产品 | 仓库 `PRODUCT_RULES.md` |
| 跨端工程红线 | Obsidian `03_工程规范` |
| 后端分层 | Obsidian `05_后端规范` |
| 迁移 / 模型 | `saas-base/MIGRATIONS.md` + Obsidian `06_数据库规范` |
| API | Obsidian `07_API规范` |
| 安全 | Obsidian `08_安全规范` |
| 前端拆分习惯 | Obsidian `04_前端规范` |
| 小程序 Overlay / primitive | **不在这里改** Constitution；先 ADR |

每条写：规则内容、适用范围、禁止行为。能标 红线/建议/参考 的，沿用知识库既有分级。

然后检查 [PROJECT_INDEX.md](./PROJECT_INDEX.md) 的链接是否仍指向正确文件。只改索引，不把规则正文抄进索引。

### 4. 产品决策

生成 ADR，追加到：

`...\05_产品决策\产品决策记录.md`

用该文件已有模板：背景、选项、决定、结果、相关 commit。交互类完整正文若按现状应落在 `产品规则.md`，ADR 日志里留标题和指针，不要两处各写一篇互相漂移的长文。

### 5. Phase 完成

在本机 `...\06_开发日志\开发日志.md` 追加阶段报告：阶段名、基线 SHA、做了什么、没做什么、验证、后续。

不把阶段报告写成新的规范文件。

---

## 不需要更新

- 文案修改
- CSS 微调
- 单页面视觉调整
- 普通代码重构（不改变合同、不改变数据模型、不改变支付/租户语义）

这些走 [AI_COMPLETION_PROTOCOL.md](./AI_COMPLETION_PROTOCOL.md) 的测试 + git 即可。

---

## 双写规则

| 情况 | 仓库 | Obsidian |
|---|---|---|
| 命令、路径、授权变化 | 必须改 `Claude.md` | `12_部署运维` 只改判断层，不复制命令 |
| 支付产品十条变化 | 必须改 `PRODUCT_RULES.md` | 同步 `01_产品规则` 或明确「以仓库为准」 |
| BUG / ADR / 阶段叙事 | hotfix ledger 可选 | 必须 |
| 无本机 vault | 只更新仓库能更新的文件，并在回复里写明 Obsidian 未写 |

不要把 Obsidian 长文复制进 git 来「备份知识库」。git 只保留入口、索引、以及已经在 git 里的合同。
