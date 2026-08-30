#!/usr/bin/env bash
# 生产配置 + 用户上传文件 的一次性可重复备份。
#
# 备份的两样东西都不在 git 里、只在生产机上（见 CLAUDE.md）：
#   - saas-base/.env          真实密钥 / 数据库口令 / DEMO_TENANT_ID / 微信支付凭证…
#   - saas-base/static/       用户上传文件（入口码 QR 图 entrance-codes/ 等）
# 机器一挂，这两样没有异地副本就彻底丢了。
#
# 用法（在生产机 root shell 里，服务不用停）：
#   bash /www/wwwroot/xiao/scripts/backup-server-config.sh
#
# 跑完会打印一条 scp 命令 —— 在你自己电脑上执行它，把 tar 包拉到本地/网盘，
# 这才算"异地"。只放在 /www/backups 下不算。
set -euo pipefail

REPO_DIR="${REPO_DIR:-/www/wwwroot/xiao}"
BACKEND_DIR="$REPO_DIR/saas-base"
ENV_FILE="$BACKEND_DIR/.env"
STATIC_DIR="$BACKEND_DIR/static"
OUT_DIR="${OUT_DIR:-/www/backups/xiao-config}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "===== config backup  TS=$TS ====="
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE 不存在"; exit 1; }
[ -d "$STATIC_DIR" ] || { echo "FAIL: $STATIC_DIR 不存在"; exit 1; }

mkdir -p "$OUT_DIR" "$STAGE/payload"
chmod 700 "$OUT_DIR"

# --- 收集 ---
cp -p "$ENV_FILE" "$STAGE/payload/env"
tar -C "$BACKEND_DIR" -czf "$STAGE/payload/static.tar.gz" static

# --- 元数据 ---
{
  echo "backup_ts_utc=$TS"
  echo "host=$(hostname)"
  echo "repo_dir=$REPO_DIR"
  echo "git_head=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "env_bytes=$(stat -c%s "$ENV_FILE")"
  echo "env_sha256=$(sha256sum "$ENV_FILE" | cut -d' ' -f1)"
  echo "env_key_count=$(grep -cE '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" || true)"
  echo "static_files=$(find "$STATIC_DIR" -type f | wc -l)"
  echo "static_bytes=$(du -sb "$STATIC_DIR" | cut -f1)"
  echo "static_tar_sha256=$(sha256sum "$STAGE/payload/static.tar.gz" | cut -d' ' -f1)"
  echo "# .env 的 key（只列 key，不列值）:"
  grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | sed 's/=$//' | sort | sed 's/^/#   /'
} > "$STAGE/payload/MANIFEST.txt"

# --- 打包 ---
ARCHIVE="$OUT_DIR/xiao-config-$TS.tar.gz"
tar -C "$STAGE/payload" -czf "$ARCHIVE" env static.tar.gz MANIFEST.txt
chmod 600 "$ARCHIVE"
sha256sum "$ARCHIVE" | tee "$ARCHIVE.sha256"

echo
echo "----- MANIFEST -----"
cat "$STAGE/payload/MANIFEST.txt"
echo "--------------------"
echo
echo "备份包: $ARCHIVE  ($(stat -c%s "$ARCHIVE") 字节)"
echo
echo "现在在【你自己的电脑】上跑这条，把它拉到本地（改成你的路径）："
echo "  scp root@iZ2ze1vb1w9yuqx7rdjwkpZ:$ARCHIVE  ~/xiao-backups/"
echo "  scp root@iZ2ze1vb1w9yuqx7rdjwkpZ:$ARCHIVE.sha256  ~/xiao-backups/"
echo
echo "拉下来后校验：  sha256sum -c xiao-config-$TS.tar.gz.sha256"
echo
echo "建议：每次改 .env 或有新用户上传后重跑一次；本地至少留最近 3 份。"
