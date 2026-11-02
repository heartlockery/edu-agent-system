#!/usr/bin/env bash
# =====================================================================
# 数据库每日备份（PostgreSQL）
# 用法：sudo bash scripts/backup_db.sh
# 产物：/opt/backups/edu_YYYYmmdd_HHMM.sql.gz，保留最近 7 份
# 定时：由 /etc/systemd/system/edu-backup.timer 每天 03:15 触发
# =====================================================================
set -euo pipefail

DB_NAME="${DB_NAME:-edu_system}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
KEEP=7

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M)"
OUT="$BACKUP_DIR/edu_$STAMP.sql.gz"

sudo -u postgres pg_dump "$DB_NAME" | gzip > "$OUT"
chmod 600 "$OUT"
echo "备份完成: $OUT ($(du -h "$OUT" | cut -f1))"

# 只保留最近 KEEP 份
ls -1t "$BACKUP_DIR"/edu_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "当前保留: $(ls -1 "$BACKUP_DIR"/edu_*.sql.gz 2>/dev/null | wc -l) 份"
