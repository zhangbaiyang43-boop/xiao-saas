# 01 — 发布架构

RELEASE_ENGINEERING_VERSION=1.0  
权威脚本：`scripts/deploy-production.sh`、`scripts/rollback-admin-h5.sh`  
权威长文：`docs/production-deployment.md`  
本文是给单人运维用的链路图，不替代上面两份文件。

## 链路

```
本机改代码
    ↓  commit + push origin/main
GitHub main
    ↓  path-filtered CI（门禁，不发布）
    ↓  admin-h5 变更时：admin-h5-release.yml
Artifact（GitHub Release 存证 + COS 运行时）
    ↓  人工在 ECS 执行 deploy-production.sh
Production（git checkout + 可选 systemd + current 软链）
```

CI **从不** SSH 到生产。生产 **从不** 跑 `vite build`。去线上永远是一次有意识的服务器命令。

## 每一步的责任

| 步 | 谁做 | 做什么 | 明确不做 |
|---|---|---|---|
| Local | 开发者 | 改代码、跑相关测试、commit | 不在本机打生产包当权威产物 |
| Git | `origin/main` | 唯一可上线的提交历史 | 生产不 commit、不用 force-push |
| CI | GitHub Actions | 证明「这个 SHA 能过门」 | 不重启服务、不切 `current` |
| Artifact | `admin-h5-release.yml` | 每个 SHA 打一份不可变前端包 | 不在 ECS 上 npm/vite |
| Release | GitHub Release + COS | Release=审计副本；COS=生产下载 | 生产不直连 github.com 下包 |
| Production | 人 + `deploy-production.sh` | ff-only pull、手跑 alembic、重启 backend、切 `current` | 不手写 SHA、不手改 nginx root |

## CI 各管一段

| Workflow | 何时 | 权威性 |
|---|---|---|
| `saas-base-ci.yml` | `saas-base/**` push/PR | 轻量：安装 + import + collect |
| `backend-candidate-certification.yml` | 候选认证 | 比 smoke 重的 P0 门 |
| `backend-full.yml` | 仅 `workflow_dispatch` | 全量 pytest，最慢、最权威 |
| `admin-h5-ci.yml` | `admin-h5/**` | `npm run check`（含 build） |
| `admin-h5-release.yml` | `admin-h5/**` 进 main，或手动 SHA | **唯一** 允许 `npm run build` 出生产包的地方 |
| `member-mini-client-ci.yml` | 小程序目录 | 测 + 构建；上线走微信后台，不走本脚本 |
| `deployment-tooling-ci.yml` | 部署脚本/文档变更 | Linux 上证明 atomic switch / 迁移 fail-closed |

## 生产两棵树

```
/www/wwwroot/xiao/                 git 权威（saas-base 源码直接跑）
/www/wwwroot/admin-h5/
  releases/<40-char-sha>/          不可变产物（index.html + assets/ + release.json）
  current -> releases/<sha>        nginx root 必须指这里
```

Backend 没有独立 artifact：ECS 上的 `/www/wwwroot/xiao` 就是运行的代码。Frontend 禁止用这份 checkout 里的 `admin-h5/src` 构建。

## 三条硬边界（脚本已实现）

1. **脏树拒绝**：`git status --porcelain` 非空 → `BLOCKED_DIRTY_PRODUCTION_TREE`。
2. **迁移先停**：`alembic/versions/**` 有 diff 则 **pull 之前** 退出 `MIGRATION_REQUIRED_MANUAL_REVIEW`。
3. **先 backend 健康，再切 current**：backend 挂了，前端 `current` 原样不动。

## 已知与文档不一致的一点

`docs/production-deployment.md` 仍写 `FIRST_MIGRATION_STATUS=NOT_YET_EXECUTED`（nginx 可能还在 `dist/`）。日常发布前先确认：

```nginx
root /www/wwwroot/admin-h5/current;
```

若仍是 `dist/`，自动化的 HTTP 校验验的是旧站，切 `current` 不会改变用户看到的页面。
