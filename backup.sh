#!/usr/bin/env bash
# TMS 项目自动备份脚本
#
# 备份内容（三类产物，全部进 backup/，并在 manifest.txt 里登记 sha256）：
#   1. 数据库：所有业务库（tms + 全部租户库 tms_tenant_*，自动发现，不再漏租户）
#   2. filestore：data/odoo/filestore（附件二进制；--numeric-owner 保 uid，恢复后需 chown 100:101）
#   3. 调研大文件：a-调研/spa.html、易途系统数据.db、et_data/、screenshots/
#
# 格式说明：数据库是 pg_dump 自定义格式再 gzip，扩展名 .dump.gz。
#   恢复：gunzip -c xxx.dump.gz | docker exec -i <db容器> psql? 不 —— 用 pg_restore：
#     gunzip -c tms__YYYYmmdd_HHMMSS.dump.gz | docker exec -i tms-db pg_restore -U odoo -d <新库> --no-owner
#   （老脚本历史产物名为 .sql.gz 但内容同样是 custom 格式，不是 SQL 文本，别用 psql < 恢复）
#
# 保留策略：数据库 14 份/库，filestore 7 份，大文件 7 份。
# 可选异盘/异地：导出 TMS_BACKUP_MIRROR=/mnt/other-disk/tms-backup 则每次备份后 rsync 同步。
set -euo pipefail

BACKUP_ROOT="/home/adai/tms/backup"
DB_BACKUP_DIR="$BACKUP_ROOT/db"
FILES_BACKUP_DIR="$BACKUP_ROOT/files"
FILESTORE_BACKUP_DIR="$BACKUP_ROOT/filestore"
MANIFEST="$BACKUP_ROOT/manifest.txt"
LOG_FILE="$BACKUP_ROOT/backup.log"

DB_CONTAINER="${DB_CONTAINER:-tms-db}"
DB_USER="${DB_USER:-odoo}"

TMS_ROOT="/home/adai/tms"
FILESTORE_SRC="$TMS_ROOT/c-系统实现/tms-platform/data/odoo/filestore"

DB_KEEP=14
FILES_KEEP=7
FILESTORE_KEEP=7
MIRROR_DEST="${TMS_BACKUP_MIRROR:-}"

TS="$(date +%Y%m%d_%H%M%S)"
FAILED=0

log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

sha_line() { # sha_line <file> -> "<sha256>  <basename>"
    printf '%s  %s\n' "$(sha256sum "$1" | cut -d' ' -f1)" "$(basename "$1")"
}

prune() { # prune <keep_n> <dir> <glob...>
    local keep=$1 dir=$2; shift 2
    # 注意：不能写 "$dir"/$@ —— 前缀只作用在 $@ 的第一个词上，
    # 其余模式会相对 CWD 展开，ls 拿不到就 exit 2 并把整个备份任务带崩。
    local -a find_args=() p
    for p in "$@"; do find_args+=(-o -name "$p"); done
    find_args=("${find_args[@]:1}")   # 去掉首个多余的 -o
    find "$dir" -maxdepth 1 -type f \( "${find_args[@]}" \) -printf '%T@\t%p\n' 2>/dev/null \
        | sort -rn | tail -n +$((keep + 1)) | cut -f2- \
        | while IFS= read -r f; do
            [ -n "$f" ] || continue
            rm -f "$f" && log "清理旧备份: $f"
          done
    return 0
}

mkdir -p "$DB_BACKUP_DIR" "$FILES_BACKUP_DIR" "$FILESTORE_BACKUP_DIR"
: >> "$MANIFEST"

# ---------- 1. 数据库备份（自动发现全部业务库） ----------
if ! DBS="$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -Atc \
        "select datname from pg_database
          where not datistemplate and datallowconn
            and datname not in ('postgres') order by 1" 2>>"$LOG_FILE")"; then
    log "ERROR: 无法枚举数据库（容器 $DB_CONTAINER 不在运行？）"
    DBS=""
    FAILED=1
fi

log "待备份数据库: ${DBS//$'\n'/ }"
while IFS= read -r db; do
    [ -z "$db" ] && continue
    DB_FILE="$DB_BACKUP_DIR/${db}__${TS}.dump.gz"
    log "开始备份数据库 $db ..."
    # 不吞 stderr；pipefail 保证 pg_dump 失败会被感知
    if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc "$db" 2>>"$LOG_FILE" | gzip > "$DB_FILE"; then
        DB_SIZE=$(du -h "$DB_FILE" | cut -f1)
        log "数据库备份完成: $DB_FILE ($DB_SIZE)"
        sha_line "$DB_FILE" >> "$MANIFEST"
    else
        log "ERROR: 数据库备份失败: $db"
        rm -f "$DB_FILE"
        FAILED=1
    fi
    # 按库各自保留 DB_KEEP 份（旧实现按目录总量裁剪，会让租户库把主库的历史挤掉）
    prune "$DB_KEEP" "$DB_BACKUP_DIR" "${db}__*.dump.gz"
done <<< "$DBS"

# 老脚本遗留的 .sql.gz 命名（内容同为 custom 格式），一并纳入保留窗口后清理
prune "$DB_KEEP" "$DB_BACKUP_DIR" 'tms_db_*.sql.gz'

# ---------- 2. filestore 备份（附件二进制） ----------
if [ -d "$FILESTORE_SRC" ]; then
    FS_FILE="$FILESTORE_BACKUP_DIR/filestore_${TS}.tar.gz"
    log "开始备份 filestore ..."
    if tar --numeric-owner -C "$(dirname "$FILESTORE_SRC")" -czf "$FS_FILE" "$(basename "$FILESTORE_SRC")" 2>>"$LOG_FILE"; then
        FS_SIZE=$(du -h "$FS_FILE" | cut -f1)
        FS_NFILES=$(tar -tzf "$FS_FILE" | grep -vc '/$')
        log "filestore 备份完成: $FS_FILE ($FS_SIZE, $FS_NFILES 个文件)"
        sha_line "$FS_FILE" >> "$MANIFEST"
    else
        log "ERROR: filestore 备份失败"
        rm -f "$FS_FILE"
        FAILED=1
    fi
    prune "$FILESTORE_KEEP" "$FILESTORE_BACKUP_DIR" 'filestore_*.tar.gz'
else
    log "WARN: filestore 目录不存在，跳过: $FILESTORE_SRC"
fi

# ---------- 3. 调研大文件备份 ----------
FILES_FILE="$FILES_BACKUP_DIR/tms_files_${TS}.tar.gz"
log "开始备份调研大文件 ..."
if tar -czf "$FILES_FILE" -C "$TMS_ROOT/a-调研" \
        spa.html 易途系统数据.db et_data screenshots 2>>"$LOG_FILE"; then
    log "大文件备份完成: $FILES_FILE ($(du -h "$FILES_FILE" | cut -f1))"
    sha_line "$FILES_FILE" >> "$MANIFEST"
else
    log "ERROR: 大文件备份失败（部分文件可能不存在）"
    rm -f "$FILES_FILE"
    FAILED=1
fi
prune "$FILES_KEEP" "$FILES_BACKUP_DIR" 'tms_files_*.tar.gz'

# ---------- 4. 可选异盘/异地镜像 ----------
if [ -n "$MIRROR_DEST" ]; then
    mkdir -p "$MIRROR_DEST"
    if rsync -a --delete "$BACKUP_ROOT/" "$MIRROR_DEST/" 2>>"$LOG_FILE"; then
        log "镜像同步完成 -> $MIRROR_DEST"
    else
        log "ERROR: 镜像同步失败 -> $MIRROR_DEST"
        FAILED=1
    fi
fi

# ---------- 5. 结论 ----------
if [ "$FAILED" -eq 0 ]; then
    log "=== 备份任务结束（OK）==="
    echo "OK: 备份完成 $TS（详见 $LOG_FILE）"
else
    log "=== 备份任务结束（有失败项）==="
    echo "FAILED: 本次备份存在失败项，见 $LOG_FILE" >&2
    exit 1
fi
