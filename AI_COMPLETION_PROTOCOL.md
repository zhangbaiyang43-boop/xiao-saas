# AI 完成协议

任务收尾标准流程。与 `Claude.md` 的「改完即 commit/push `main`」授权同时生效：本文件规定顺序，不取消那条授权。

```
代码修改完成
    ↓
运行相关测试（通过才能声称完成）
    ↓
判断是否产生长期知识（见 AI_MEMORY_UPDATE_PROTOCOL.md）
    ↓
需要 → 更新对应 docs / Obsidian / 索引链接
    ↓
若本次属于必须更新知识的那五类：追加 CHANGELOG 一条
    ↓
git commit + push origin main
```

不需要更新知识库时：测试通过后直接提交代码，不要为了「流程完整」空写 ADR。

---

## 1. 测试

按影响端跑最小相关集，不要假装跑过。

| 端 | 最小验证 |
|---|---|
| `saas-base` | 相关 pytest；动到隔离/模型时包含 `tests/test_tenant_isolation_scan.py`；动到迁移时 `alembic heads` |
| `member-mini-client` | 在 `member-mini-client/` 下跑项目 vitest / 相关脚本，不要用仓库根的 npx vitest 扫 worktree |
| 前端合同 | 触及 overlay/mask/sheet 时：`npm run check:ui-contracts` |
| `admin-h5` | 相关 `npm run test:*` 或页面级脚本；编码问题跑 `npm run check:text` |
| 生产部署文档/脚本 | 不要在生产服务器上验证 git push |

测试失败不得 commit 为「完成」。

## 2. 长期知识

只在 [AI_MEMORY_UPDATE_PROTOCOL.md](./AI_MEMORY_UPDATE_PROTOCOL.md) 列出的五类发生时更新。

## 3. CHANGELOG

仓库根 `CHANGELOG.md` 目前可以不存在。

- 若本次触发了必须更新知识库的类型：创建或追加 `CHANGELOG.md` 一条（日期、SHA、一句话、影响端）。
- 文案 / CSS / 单页视觉 / 普通重构：不写 CHANGELOG。

## 4. Git

遵守 `Claude.md`：

- 常规完成：commit + push `origin main`，不必再问
- 先跑相关测试
- 提交信息写清改了什么、为什么
- force-push / reset --hard / 改写历史：先问
- 回复里必须写清影响 `member-mini-client` / `saas-base` / `admin-h5` 的哪一端

不要提交：`.env`、`saas-base/venv`、`saas-base/static/`、本机 Obsidian 文件、`_final_*_worktrees`、无名 `git` 残留文件。

## 5. 回复收尾

用三端影响句结束，例如：

`影响端：member-mini-client。saas-base / admin-h5 无改动。小程序需微信开发者工具发版后才到线上。`
