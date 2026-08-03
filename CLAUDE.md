# Git workflow — standing authorization

After finishing a code change in this repo, commit and push to `origin main` on GitHub
**without asking for confirmation first**. This overrides the default "ask before commit/push"
behavior — the user has explicitly authorized always-on auto-commit-and-push for this repo.

- Still write clear, accurate commit messages describing what changed and why.
- Still run the relevant tests before committing.
- If a push is blocked by a tool permission classifier, hand the user the exact command to run
  in **Git Bash** (not the production server) rather than retrying silently.
- This standing authorization covers routine commit/push only. Destructive git operations
  (force-push, reset --hard, history rewrites) still require asking first, same as always.

# Deployment facts (learned the hard way — don't rediscover these)

- **GitHub remote**: `git@github.com:zhangbaiyang43-boop/xiao-saas.git`, branch `main`.
  Local push uses a dedicated key `~/.ssh/id_ed25519_github`; the machine also has a global
  git config rule rewriting `git@github.com:` → `https://...` (`url.https://github.com/.insteadof`)
  which sometimes causes "Empty reply from server" over HTTPS — if push/fetch fails that way,
  retry with `GIT_CONFIG_GLOBAL=/dev/null` to bypass the global config and force real SSH.
- **Production server**: `root@iZ2ze1vb1w9yuqx7rdjwkpZ` (Alibaba Cloud ECS). The whole monorepo
  is checked out at `/www/wwwroot/xiao` (contains `.git`); the backend app itself lives at
  `/www/wwwroot/xiao/saas-base`. The server has its own **read-only** deploy key
  (`~/.ssh/id_ed25519_deploy`, configured in `~/.ssh/config` for `Host github.com` so plain
  `git pull`/`git fetch` just works, no SSH_COMMAND prefix needed).
- **Server never commits** — the deploy key is read-only on purpose. If a server-side git
  operation asks for a commit identity or tries to push, stop and do the change from the local
  machine instead, then have the server `git pull`.
- **Server Python is 3.12** (via `python3.12`, apt-installed), not 3.10 — local dev `.venv` is
  3.10. When diagnosing dependency/version issues, check both, don't assume the versions match.
- **`saas-base/venv` is never committed and never portable** — a venv's wrapped scripts
  (`bin/uvicorn`, `bin/pip`, etc.) hardcode the absolute path they were created at. If the app
  directory ever moves, rebuild the venv in place (`python3.12 -m venv venv && pip install -r
  requirements.txt`) — never `cp -r` an existing venv to a new path.
- **`.env` and `saas-base/static/` are not in git** — they hold real secrets and user-uploaded
  files (entrance-code QR images, etc.) that only exist on the server. Any time the app directory
  is rebuilt/relocated, these two must be copied over by hand from the previous location.
- **`cp -r src dst` nests one level deep if `dst` already exists** — this bit us twice (once with
  `static/`, once conceptually with the venv). Before copying a directory into a path that a fresh
  `git checkout` may have already recreated, check whether `dst` exists first.
- **Production COS bucket is `poster-system-1253573799`** (`COS_BUCKET` in the server's `.env`).
  Confirmed in the Tencent Cloud console: 基础图片处理/数据万象 is already enabled on this bucket
  and 原图保护 is off, so the `imageMogr2/thumbnail/{size}x/format/webp` query-param thumbnails
  appended in `member-mini-client` (`dishImage()` in `menu.vue`) work without any extra "样式"
  setup — the raw-query-param access pattern is the default-supported one. If dish images are
  ever migrated to a different bucket, re-check this setting on the new bucket; it's per-bucket,
  not account-wide.

## Standard deployment recipe (once code is on GitHub)

```bash
# On the server:
cd /www/wwwroot/xiao
git pull origin main

cd saas-base
# Only if dependencies changed:
source venv/bin/activate && pip install -r requirements.txt
# Only if there's a new migration:
alembic upgrade head

systemctl restart saas-base.service
journalctl -u saas-base.service -n 20 --no-pager
```

Note: `admin-h5` (static SPA build) and `member-mini-client` (WeChat mini-program, published via
WeChat DevTools + mp.weixin.qq.com review) have separate, different deployment paths — this
recipe only covers the `saas-base` backend.
