# 02 — Admin Artifact Contract

一个 SHA 一份包。路径里带 SHA，内容不可变。生产只下载、校验、解压，不构建。

## 必须存在的根文件

解压后 **没有** 嵌套 `dist/`。根上必须是：

| 条目 | 规则 |
|---|---|
| `index.html` | 非空文件 |
| `assets/` | 目录（带 hash 的 JS/CSS） |
| `release.json` | 非空；`sha` 必须等于该目录名 / 目标 git SHA |

`release.json` 形状：

```json
{
  "sha": "<40-char git sha>",
  "built_at": "<UTC ISO8601>",
  "builder": "github-actions"
}
```

不含密钥。`built_at` 每次构建会变，**比较是否同一产物时忽略它**。

## 命名

```
GitHub Release tag:  admin-h5-<FULL_SHA>
Archive:             admin-h5-dist-<FULL_SHA>.tar.gz
Checksum:            admin-h5-dist-<FULL_SHA>.tar.gz.sha256
COS key:             deploy-artifacts/admin-h5/admin-h5-<FULL_SHA>/...
Disk:                /www/wwwroot/admin-h5/releases/<FULL_SHA>/
```

一律 **40 位完整 SHA**。短 SHA 不是合法 release 目录名。

## 谁生成

只有 `.github/workflows/admin-h5-release.yml`：

1. checkout 目标 SHA，并对一下 HEAD。
2. `admin-h5/` 里 `npm ci && npm run build`。
3. 把 `dist/` 摊平到 archive 根，写入 `release.json`。
4. `sha256sum` 出 `.sha256`。
5. **publish 任务**（非 PR）：GitHub Release 存证 + `scripts/publish-admin-artifact-cos.py` 上传 COS。
6. 再用 **公开 HTTPS GET** 把 COS 上的包下回来跑 `sha256sum -c`。上传成功 ≠ 生产能下到。

PR 只跑 build，不 publish。`contents:write` 碰不到未合并的 PR 代码。

生产 **禁止** `npm` / `npx` / `vite`（`scripts/test-deployment-tooling.sh` 盯着 deploy 脚本）。

## 生产如何验收

`scripts/deploy-production.sh` 里的 `release_is_valid <dir> <expected-sha>`：

1. `index.html` 存在且非空。
2. `assets/` 是目录。
3. `release.json` 存在且非空。
4. `release.json` 的 `sha` **全等** 于期望的 40 位 SHA。
5. 下载后：`sha256sum -c`。
6. 解压前：`archive_is_safe`（拒绝绝对路径、`..`、符号链接/设备文件）。
7. 先解到 `mktemp` 目录，校验通过再 `mv -T` 成 `releases/<sha>`。已有目录若校验失败：**拒绝覆盖**（`BLOCKED_INVALID_EXISTING_RELEASE`）。

`rollback-admin-h5.sh` 用同一套校验。目录不存在或 `sha` 对不上 → `BLOCKED_UNKNOWN_RELEASE`，**不切** `current`。

## 失败码（前端包）

| STATUS | 含义 | 人怎么做 |
|---|---|---|
| `ADMIN_ARTIFACT_NOT_READY` | COS 还没有这对文件 | 等 `admin-h5-release` 绿了再跑 |
| `BLOCKED_ADMIN_ARTIFACT_CHECKSUM` | 校验和不配 | 停；不要手解压 |
| `BLOCKED_UNSAFE_ADMIN_ARTIFACT` | tar 里有危险条目 | 停 |
| `BLOCKED_INVALID_ADMIN_ARTIFACT` | 缺文件或 json sha 不对 | 停 |
| `BLOCKED_INVALID_EXISTING_RELEASE` | 磁盘上已有坏目录 | 停；不要 `rm -rf` 后重来，先看清 |
| `BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED` | 没有 `ARTIFACT_BASE_URL` | 写 `/etc/xiao-deploy.env` 再跑 |
| `BLOCKED_UNKNOWN_RELEASE` | rollback 目标不合格 | `ls -1t releases/`，复制真实目录名 |

## 人不要做的

- 不要自己敲 SHA。从 `git rev-parse origin/main` 或 `ls /www/wwwroot/admin-h5/releases` 复制。
- 不要把 GitHub Release URL 填进 `ARTIFACT_BASE_URL`（国内下载会超时）。
- 不要在 ECS 上为了「包还没好」而 `npm run build`。
