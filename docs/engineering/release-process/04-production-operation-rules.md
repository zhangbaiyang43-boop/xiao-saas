# 04 — 生产操作禁令

这些不是风格问题。违反过就会 500 或静默上错包。

## 禁止人工输入 SHA

不要在 `ln`、`checkout`、`rollback`、nginx `root` 里手打 hash。

允许的 SHA 来源只有：

- `git rev-parse HEAD` / `git rev-parse origin/main`
- `cat /www/wwwroot/admin-h5/current/release.json`
- `ls -1t /www/wwwroot/admin-h5/releases` 的**完整目录名**

短 SHA、凭记忆、从聊天里抄半截，都禁止。`rollback-admin-h5.sh` 按目录名精确匹配；少一位就是 `BLOCKED_UNKNOWN_RELEASE`——若绕过脚本，nginx 就会指到不存在的路径。

## 禁止手动改 `current`

禁止：

```bash
ln -sfn /www/wwwroot/admin-h5/releases/<sha> /www/wwwroot/admin-h5/current
rm /www/wwwroot/admin-h5/current
ln -s ... current
```

只允许：

- `scripts/deploy-production.sh`（例行切链）
- `scripts/rollback-admin-h5.sh <sha>`（回滚）

两者都是 `ln -sfn … current.new` + `mv -Tf`，nginx 不会看到缺失的 `current`。手 `ln` 没有「目录必须存在 / json sha 必须匹配 / 失败拨回」这三道闸。

## 禁止改 nginx root 来切版本

`root` 只能是：

```nginx
root /www/wwwroot/admin-h5/current;
```

禁止 `root …/releases/<sha>`，禁止改回 `…/dist`（cutover 完成后）。例行发布 **不 reload nginx**。

## 禁止绕过 deploy 脚本

禁止用这一套代替 `./scripts/deploy-production.sh`：

- 裸 `git pull` + 手 `systemctl restart` + 手切前端（会忘掉 health 门、包校验、顺序）
- FTP/SFTP 上传 `dist/`
- 在 `/www/wwwroot/admin-h5/src` 里改文件
- 第二份 git checkout
- `git reset --hard` / `git clean -fd` 自动「修好」脏树

脏树：先看是什么文件。`.env` 和 `saas-base/static/` 本来就不在 git 里。

## 禁止在生产构建前端

主机内存约 1.6 GiB。`vite build` 会把机器打满。

禁止在 ECS 上：`npm ci`、`npm run build`、`npx vite`、`node_modules` 救火。包只来自 GitHub Actions → COS。

## 禁止未校验的 release 上线

`releases/<sha>` 在 `release_is_valid` 之前对 nginx 不可见。禁止：

- 解 tar 到一个「差不多」的目录就切 `current`
- 覆盖校验失败的已有目录
- 跳过 `sha256sum -c`
- 用 GitHub Release URL 当 `ARTIFACT_BASE_URL`

## 禁止自动跑 alembic

脚本在 pull **之前** 遇到 `alembic/versions/**` 就会停。不要改脚本去自动 `upgrade`。

也不要：

- 在生产 **写** 新 migration
- `alembic stamp` 来「对齐一下」而不读 diff
- migration 失败后不看 SQL 就 downgrade

## 禁止生产 commit / push

部署钥只读。身份和推送只在开发机。服务器 `git pull --ff-only`。

## 禁止无 --force 的 migration 续发

手 pull + `alembic upgrade` 之后，`BEFORE_SHA == TARGET_SHA`，裸跑脚本是 no-op。必须 `--force-backend`，admin 有变再 `--force-admin`。

## 禁止并行部署

同一次只一个 `deploy-production.sh`。不要两个 Workbench 窗口一起 pull。

## 禁止用开发机代替生产真相

开发机没有生产 SSH 钥时，不要把「GitHub 已是某 SHA」说成「生产已是某 SHA」。生产真相只有：

```text
ECS git HEAD
current/release.json
systemctl is-active saas-base.service
curl /health
```
