#!/usr/bin/env bash
# TMS 项目自动备份脚本
# 备份内容：
#   1. PostgreSQL 数据库 (tms) — pg_dump 逻辑备份
#   2. 调研大文件（gitignore 排除，不在 GitHub 上）
#      - a-调研/spa.html
#      - a-调研/易途系统数据.db
#      - a-调研/et_data/
#      - a-调研/screenshots/
# 保留策略：数据库 14 份，大文件 7 份（旧文件自动清理）

set -euo pipefail

# 配置
BACKUP_ROOT="/home/adai/tms/backup"
DB_BACKUP_DIR="$BACKUP_ROOT/db"
FILES_BACKUP_DIR="$BACKUP_ROOT/files"
LOG_FILE="$BACKUP_ROOT/backup.log"

DB_CONTAINER="tms-db"
DB_USER="odoo"
DB_NAME="tms"

TMS_ROOT="/home/adai/tms"

DB_KEEP=14   # 数据库备份保留份数
FILES_KEEP=7 # 大文件备份保留份数

TS="$(date +%Y%m%d_%H%M%S)"

log() {
    echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"
}

# 初始化目录
mkdir -p "$DB_BACKUP_DIR" "$FILES_BACKUP_DIR"

# ---------- 1. 数据库备份 ----------
DB_FILE="$DB_BACKUP_DIR/tms_db_${TS}.sql.gz"
log "开始备份数据库 $DB_NAME ..."

if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" 2>/dev/null | gzip > "$DB_FILE"; then
    DB_SIZE=$(du -h "$DB_FILE" | cut -f1)
    log "数据库备份完成: $DB_FILE ($DB_SIZE)"
else
    log "ERROR: 数据库备份失败（容器 $DB_CONTAINER 不在运行？）"
fi

# 清理旧数据库备份
ls -1t "$DB_BACKUP_DIR"/tms_db_*.sql.gz 2>/dev/null | tail -n +$((DB_KEEP + 1)) | while read -r f; do
    rm -f "$f"
    log "清理旧数据库备份: $f"
done

# ---------- 2. 调研大文件备份 ----------
FILES_FILE="$FILES_BACKUP_DIR/tms_files_${TS}.tar.gz"
log "开始备份调研大文件 ..."

tar -czf "$FILES_FILE" \
    -C "$TMS_ROOT/a-调研" \
    spa.html \
    易途系统数据.db \
    et_data \
    screenshots \
    2>>"$LOG_FILE" || log "ERROR: 大文件备份失败（部分文件可能不存在）"

FILES_SIZE=$(du -h "$FILES_FILE" 2>/dev/null | cut -f1)
log "大文件备份完成: $FILES_FILE ($FILES_SIZE)"

# 清理旧大文件备份
ls -1t "$FILES_BACKUP_DIR"/tms_files_*.tar.gz 2>/dev/null | tail -n +$((FILES_KEEP + 1)) | while read -r f; do
    rm -f "$f"
    log "清理旧大文件备份: $f"
done

log "=== 备份任务结束 ==="
