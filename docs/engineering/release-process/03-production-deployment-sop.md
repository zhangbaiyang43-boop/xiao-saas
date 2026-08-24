# 03 — 生产发布 SOP

单人、低步骤。默认一条命令。唯一例外：数据库 migration。

目标环境：阿里云 ECS，`/www/wwwroot/xiao`，服务 `saas-base.service`，站点 `https://saas.zhangbaiyang.com/`，API `https://api.zhangbaiyang.com/health`。

## 发布前

在 **ECS root shell**（Workbench 或已配置部署钥的机器），不要在开发 Windows 上猜生产状态。

```bash
# 1. 工作树必须干净
cd /www/wwwroot/xiao
git status --porcelain          # 必须空。有输出就停，先查，禁止 git reset --hard

# 2. 现在线上是哪一版
git rev-parse HEAD
test -f /www/wwwroot/admin-h5/current/release.json \
  && cat /www/wwwroot/admin-h5/current/release.json

# 3. nginx 必须跟 current，不能跟死 SHA 或旧 dist
grep -n 'root ' /www/server/panel/vhost/nginx/saas.zhangbaiyang.com.conf \
  || grep -n 'root ' /etc/nginx/sites-enabled/*saas* /etc/nginx/conf.d/* 2>/dev/null
# 期望：root /www/wwwroot/admin-h5/current;

# 4. 看 main 要上什么
git fetch origin
echo "NOW    $(git rev-parse HEAD)"
echo "TARGET $(git rev-parse origin/main)"
git log --oneline HEAD..origin/main

# 5. 这包会不会动库 / 前端
git diff --name-only HEAD origin/main -- saas-base/alembic/versions/
git diff --name-only HEAD origin/main -- admin-h5/
git diff --name-only HEAD origin/main -- saas-base/

# 6. 若 admin-h5 有改动：COS 上这个 SHA 的包必须已经在
#    等 GitHub Actions「admin-h5 Release Artifact」成功。不要手建。
```

`/etc/xiao-deploy.env` 需要一行（不要放密钥）：

```
ARTIFACT_BASE_URL=<public COS base>/deploy-artifacts/admin-h5
```

## 无 migration：一条命令

```bash
cd /www/wwwroot/xiao
./scripts/deploy-production.sh
# 预期最后一行：STATUS=DEPLOY_OK
# 记下 DEPLOYED_SHA=
```

脚本会：拒绝脏树 → fetch → 若有 alembic 文件则停 → 需要前端包则检查 COS 配置 → `git pull --ff-only` → 下载并校验 admin 包（如需要）→ 如需要则 pip + `systemctl restart saas-base.service` + `/health` → **健康后再** `ln -sfn` + `mv -Tf` 切 `current` → curl 首页须含 `/assets/`，失败则把 `current` 拨回去。

`--dry-run` 只打印，不写盘。

## 有 migration：手跑，禁止让脚本 migrate

`deploy-production.sh` **不会** `alembic upgrade`。看到 `MIGRATION_REQUIRED_MANUAL_REVIEW` 时 HEAD 仍是旧的。不要裸着重跑脚本指望它接着干。

```bash
cd /www/wwwroot/xiao
PRE=$(git rev-parse HEAD)
git fetch origin
TARGET=$(git rev-parse origin/main)

git status --porcelain
git diff "$PRE" "$TARGET" -- saas-base/alembic/versions/

git checkout main
git pull --ff-only origin main
test "$(git rev-parse HEAD)" = "$TARGET"

cd saas-base
source venv/bin/activate
python3.12 -m alembic heads          # 单 head
python3.12 -m alembic current
python3.12 -m alembic upgrade head   # 只跑已经进 git 的 revision
python3.12 -m alembic current        # 须等于 heads
cd /www/wwwroot/xiao

# pull 之后 BEFORE==TARGET，脚本会认为「没变化」——必须 --force-*
./scripts/deploy-production.sh --force-backend --force-admin
```

只有 backend 变了就 `--force-backend`。admin 也变了再加 `--force-admin`。

## 发布后

```bash
# Backend
git rev-parse HEAD                   # = 刚才的 TARGET
systemctl is-active saas-base.service
curl -sS http://127.0.0.1:9898/health
curl -sS https://api.zhangbaiyang.com/health
journalctl -u saas-base.service -n 30 --no-pager

# Admin：release.json.sha 必须等于 git HEAD；index 的 /assets/index-*.js 须对应该产物
cat /www/wwwroot/admin-h5/current/release.json
readlink -f /www/wwwroot/admin-h5/current
curl -sS https://saas.zhangbaiyang.com/ | head

# 业务：用 owner 账号点一下当前订单 / 历史订单（若本版包含历史查询）
```

任一步对不上 SHA：**不要**再 `ln`。用下面 rollback。

## Rollback

### 只回前端（秒级，不 checkout）

```bash
ls -1t /www/wwwroot/admin-h5/releases
# 复制完整目录名，不要手打
cd /www/wwwroot/xiao
./scripts/rollback-admin-h5.sh <40-char-sha>
# STATUS=ROLLBACK_OK
cat /www/wwwroot/admin-h5/current/release.json
```

脚本会先验包再切链；HTTP 失败会切回原 `current`。

### 回 backend

没有自动脚本。有意为之。

```bash
cd /www/wwwroot/xiao
git log --oneline -5
git checkout <known-good-sha>     # 仅当该区间没有 alembic
systemctl restart saas-base.service
curl -sS http://127.0.0.1:9898/health
```

区间里有 migration：先定「只回代码」还是「代码+库」。**不要**随手 `alembic downgrade`。先停发布，再决定。

## 不要走的捷径

| 冲动 | 改为 |
|---|---|
| `ln -sfn /www/wwwroot/admin-h5/releases/<我记的sha> current` | `rollback-admin-h5.sh` + 从 `ls` 粘贴 |
| 改 nginx `root` 到某个 `releases/<sha>` | `root` 永远是 `.../current` |
| ECS 上 `npm run build` | 等 Actions；`ADMIN_ARTIFACT_NOT_READY` 就等 |
| 脚本因 migration 停下后直接再跑一遍 | 手跑 alembic，再 `--force-backend/--force-admin` |
| Windows 开发机上「大概部署了」 | 只以 ECS 上的 `HEAD` + `current/release.json` 为准 |
