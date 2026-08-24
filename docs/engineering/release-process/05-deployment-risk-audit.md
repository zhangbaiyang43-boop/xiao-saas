# 05 — 发布风险审计 + Incident Postmortem

审计基准：仓库 `main`（含 `scripts/deploy-production.sh`、`rollback-admin-h5.sh`、`admin-h5-release.yml`）。  
代码未改。结论服务「单人维护、低复杂度、少出事」。

## 总评

工具链设计是对的：SHA 寻址包、原子切链、迁移 fail-closed、先 backend 后 frontend。  
真正的 P0 不在脚本内部，而在 **脚本可以整段被绕过**，以及 **首次 nginx cutover 可能仍未完成**。绕过时，所有自动化保护都等于零。

RELEASE_PROCESS_STATUS 见文末。

---

## P0

### P0-1 手切 `current` / 手写 SHA → nginx 指空目录 → 500

- **位置：** 人在 ECS 上 `ln -s`；或 nginx `root` 写成 `releases/<打错的sha>`。不是 deploy 脚本里面。
- **原因：** 保护写在 `deploy-production.sh` / `rollback-admin-h5.sh` 里。OS 不阻止 root 把 `current` 指到不存在的路径。手打 40 位 SHA 极易错一位。
- **影响：** `saas.zhangbaiyang.com` 整站 500。Backend 可能仍健康，收银/接单前端不可用。
- **建议（小改，保持简单）：**
  1. 操作纪律：只允许 rollback 脚本切链（见 `04`）。
  2. 不要扩展 deploy 脚本接收「任意 SHA」参数。
  3. 可选（约 20 行）：`scripts/switch-admin-current.sh` 作为唯一入口，内部只调用已有 `release_is_valid`；再加一条 crontab/`command` 别名提示「不要 ln current」。不要上新平台。

详见下面 Postmortem。

### P0-2 nginx 仍指向 `dist/` 时，切 `current` 不改变用户看到的站

- **位置：** `docs/production-deployment.md` 写明 `FIRST_MIGRATION_STATUS=NOT_YET_EXECUTED`。
- **原因：** 例行校验 curl 的是 `PRODUCTION_URL`。若 root 还是 `dist/`，校验的是旧树；`current` 切了对访客无影响。
- **影响：** 「DEPLOY_OK」但商家后台仍是旧 bundle（P1-02 认证见过 live `index-BdVtd5Vt.js` ≠ 目标产物）。
- **建议：** 发布前 `grep root` 配置。若不是 `.../current`，先做文档里的一次性 cutover，再例行发布。不要边发版边改 nginx，除非正在做 cutover。

### P0-3 生产构建前端把 ECS 打满

- **位置：** 主机 ~1.6 GiB RAM；历史 `vite build`。
- **原因：** 救火时「包还没好，我在服务器编一下」。
- **影响：** 整机无响应，backend 一并挂。
- **建议：** 已禁止。`ADMIN_ARTIFACT_NOT_READY` = 等 Actions，不是在 ECS 开 node。

---

## P1

### P1-1 migration 之后忘了 `--force-*`

- **位置：** `deploy-production.sh` 在 `BEFORE==TARGET` 时把变更位清零。
- **原因：** 手 pull 后脚本以为没活干。
- **影响：** 库已经 upgrade，进程还是旧代码；或代码已 pull 但没 restart。
- **建议：** SOP 把 `--force-backend/--force-admin` 写死在 migration 段。不要做自动 resume（会悄悄跑完未审的 migrate）。

### P1-2 开发机发不了布，生产真相对不上 GitHub

- **位置：** 工作站只有 GitHub 钥，没有 ECS 钥。
- **原因：** 发布被设计成「人在服务器上执行」。这是对的，但远端代理若假装「已经发布」会误判。
- **影响：** 认证阶段 BLOCKED，功能在 main 上却不在线上。
- **建议：** 保持「只在 ECS 上发布」。加一张检查清单：HEAD、`release.json`、health。不要为了方便把生产钥放进开发机代理。

### P1-3 backend 回滚靠手 `git checkout`

- **位置：** 文档写明 frontend rollback 自动化、backend 不自动。
- **原因：** 有意避免脚本 downgrade 数据库。
- **影响：** 压力下 checkout 错 SHA，或忘掉 restart。
- **建议：** 保持手滚。回滚时把 SHA 从 `git log` 复制。有 alembic 的区间不要当常规 rollback。

### P1-4 前端 HTTP 门只看「HTML 里有 `/assets/`」

- **位置：** `deploy-production.sh` 切链后 `grep /assets/`。
- **原因：** 简单、无浏览器。
- **影响：** 旧站若也有 `/assets/`，切错也可能「过」。对不上具体 `index-*.js`。
- **建议：** 加一行：`curl` 的 index 里的 `index-*.js` 必须存在于 `$ADMIN_CURRENT/assets/`。不要上合成监测平台。

### P1-5 保留策略可能删掉你还想回的包

- **位置：** 成功切链后保留 `current` + 至少 3 个其它目录。
- **原因：** 磁盘。
- **影响：** 想回一周前的前端，目录没了，只能重新下 COS（可以，但不是秒级）。
- **建议：** 回滚只用 `ls -1t releases` 里还在的。需要更老的：再跑一次 deploy 下 COS，不要手解压。

### P1-6 alembic 与代码顺序靠人

- **位置：** 手 `upgrade` 再 `--force-backend`。
- **原因：** 正确（迁移要看）。
- **影响：** 先 restart 后 migrate → 新代码撞缺列/缺索引。
- **建议：** SOP 顺序已经是 pull → upgrade → force restart。不要对调。

---

## P2

### P2-1 GitHub Release 不是生产运输

- 有意的（国内超时）。COS 挂了不能自动回 GitHub。接受；修 COS，不要改 URL。

### P2-2 小程序不在这条链上

- 微信后台审核。后端先发、小程序后发时，注意 API 兼容，不要做小程序自动发布。

### P2-3 无部署锁

- 两个 root 窗口对打。单人操作则低。需要时：`flock -n /var/lock/xiao-deploy.lock`。

### P2-4 `chown www:www` 失败只打日志

- 权限不对会 403 而不是 500。cutover 后看一次 `ls -ld current releases`。

---

## Incident Postmortem：手切 current + SHA 打错 → 500

### 发生了什么

Admin artifact **已经**在 COS / `releases/<正确sha>/` 里。操作者没有跑 `deploy-production.sh` 或 `rollback-admin-h5.sh`，而是：

```bash
ln -sfn /www/wwwroot/admin-h5/releases/<打错的SHA> /www/wwwroot/admin-h5/current
```

或把 nginx `root` 改成那个路径。目录不存在。nginx 打不开 `index.html`。`saas.zhangbaiyang.com` 500。

### 时间线（模式）

1. Actions 已为某 SHA 出包（好事）。
2. 有人想「包都有了，切一下就行」，跳过脚本。
3. SHA 来自聊天/短 hash/手打。
4. `ln` 成功（对不存在的目标，ln 也常成功）。
5. 没有 `release_is_valid`，没有 curl `/assets/`，没有自动拨回。
6. 用户 500；API `/health` 可能仍是 200。

### 自动化为什么没拦住

不是脚本 bug。闸门在脚本入口，不在文件系统。

| 保护 | 走脚本时 | 手 ln / 改 nginx 时 |
|---|---|---|
| `release_is_valid`（index + assets + json sha） | 切之前挡下 | 不跑 |
| `ln … current.new` + `mv -Tf` | nginx 始终能看到 current | 手 ln 可能先删后建 |
| 切后 curl，失败拨回 | 会拨回 | 不跑 |
| SHA 来自 `origin/main`，不是 argv | deploy 不接受人打的 SHA | 人就是 SHA 源 |
| rollback 未知目录 → `BLOCKED_UNKNOWN_RELEASE` | 挡下 | 没调用 rollback |

`rollback-admin-h5.sh <错误sha>` 会拒绝。事故需要 **连 rollback 都没用**。

### 根因

1. `current` 对 root 可写，无强制包装。
2. 文化上「包已经在了 = 可以手切」。
3. 40 位 SHA 不是人能可靠复述的。
4. nginx 若曾指具体 `releases/<sha>`，等于每次发版改配置，错一次就 500。

### 怎么避免（按性价比）

1. **立刻、零代码：** 禁令见 `04`。切链只准两个脚本。SHA 只从 `ls` / `release.json` / `git rev-parse` 粘贴。nginx root 只准 `current`。
2. **立刻、查一次：** `grep root` 配置。不是 `current` 就按文档做一次性 cutover。
3. **很小的加固（可选）：** 包装脚本拒绝短 SHA（`[ ${#1} -eq 40 ]`）；`rollback` 已近似如此（目录必须存在）。不要做「模糊匹配短 SHA」——那会切错包。
4. **不要做：** Kubernetes、新 CD 平台、webhook 自动 deploy、让 CI SSH 进 ECS。复杂度和密钥面都涨。

### 检测 / 恢复

```bash
readlink -f /www/wwwroot/admin-h5/current
ls /www/wwwroot/admin-h5/current/index.html
ls -1t /www/wwwroot/admin-h5/releases
cd /www/wwwroot/xiao
./scripts/rollback-admin-h5.sh <从 ls 粘贴的40位sha>
```

若 nginx root 被改走：改回 `.../current`，`nginx -t`，`systemctl reload nginx`（reload 不是 restart）。

### 教训

Artifact 存在 ≠ 已上线。上线 = **脚本切过的、校验过的 `current`**。人一当 SHA 路由器，不可变包也救不了空目录。

---

## NEXT_RECOMMENDATIONS（只三条，小步）

1. **完成并冻结 nginx → `current` 的 cutover**（若尚未做），之后例行发布不再碰 nginx。
2. **切链后校验「HTML 里的 `index-*.js` 文件确实在 current/assets 里」**——一行 grep，不是新系统。
3. **migration SOP 印成 ECS 上的 motd 或 `deploy-production.sh` 的注释头部再抄一段 `--force-*`**，降低忘 force 的概率。不要自动 resume。
