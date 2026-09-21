#!/usr/bin/env bash
# A0 备份恢复演练：把最新一次备份恢复到一次性容器，与生产库做逐表行数/金额/内容指纹比对。
#
# 这是 A1 平桥的前置 gate：未通过恢复演练的备份不允许当作平桥输入。
# 演练全程只读生产库，恢复目标是一次性容器 tms-drill-db（127.0.0.1:5435），退出时删除。
#
# 判据分两级：
#   关键指纹（md5|* 内容指纹、sum|* 金额合计、count|* 核销不变量）必须 0 差异 —— 有差异说明
#     备份本身不可信，直接 FAIL；
#   逐表行数允许因"备份时刻 → 演练时刻"的在线写入产生差异（演练时无法冻结生产写入），
#     这类差异单列成表供人工确认；A1 平桥时会先冻结 cron/写入，届时要求全量 0 差异。
#
# 用法：
#   bash scripts/migration/backup_restore_drill.sh            # 演练最新 tms 备份
#   DB_DUMP=/path/x.dump.gz bash scripts/migration/backup_restore_drill.sh
set -euo pipefail

TMS_ROOT="/home/adai/tms"
PLAT="$TMS_ROOT/c-系统实现/tms-platform"
BACKUP_DB_DIR="$TMS_ROOT/backup/db"
BACKUP_FS_DIR="$TMS_ROOT/backup/filestore"

PROD_CONTAINER="${PROD_CONTAINER:-tms-db}"
PROD_DB="${PROD_DB:-tms}"
DRILL_CONTAINER="${DRILL_CONTAINER:-tms-drill-db}"
DRILL_PORT="${DRILL_PORT:-5435}"
DRILL_DB="${DRILL_DB:-drill_tms}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"

DB_DUMP="${DB_DUMP:-$(ls -1t "$BACKUP_DB_DIR"/${PROD_DB}__*.dump.gz "$BACKUP_DB_DIR"/${PROD_DB}_db_*.sql.gz 2>/dev/null | head -1 || true)}"
FS_TAR="${FS_TAR:-$(ls -1t "$BACKUP_FS_DIR"/filestore_*.tar.gz 2>/dev/null | head -1 || true)}"
TS="$(date +%Y%m%d_%H%M%S)"
WORK="$(mktemp -d /tmp/tms-drill.XXXXXX)"
REPORT_DIR="$TMS_ROOT/d-交付验收"
REPORT="${REPORT:-$REPORT_DIR/A0-备份恢复演练_${TS}.md}"

[ -n "$DB_DUMP" ] || { echo "FAIL: 在 $BACKUP_DB_DIR 找不到 ${PROD_DB} 的备份文件"; exit 1; }
echo "使用数据库备份: $DB_DUMP"
echo "使用 filestore 备份: ${FS_TAR:-（无，跳过附件演练）}"

cleanup() {
    docker rm -f "$DRILL_CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

docker rm -f "$DRILL_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$DRILL_CONTAINER" -e POSTGRES_USER=odoo -e POSTGRES_HOST_AUTH_METHOD=trust \
       -p "127.0.0.1:$DRILL_PORT:5432" "$PG_IMAGE" >/dev/null

for _ in $(seq 1 60); do
    docker exec "$DRILL_CONTAINER" pg_isready -U odoo >/dev/null 2>&1 && break
    sleep 1
done
docker exec "$DRILL_CONTAINER" pg_isready -U odoo >/dev/null || { echo "FAIL: 演练容器未就绪"; exit 1; }

docker exec "$DRILL_CONTAINER" createdb -U odoo "$DRILL_DB"
echo "恢复中（约数分钟）..."
RESTORE_LOG="$WORK/pg_restore.log"
if gunzip -c "$DB_DUMP" | docker exec -i "$DRILL_CONTAINER" pg_restore -U odoo -d "$DRILL_DB" \
        --no-owner --role=odoo 2>"$RESTORE_LOG"; then
    RESTORE_NOTE="pg_restore 无告警"
else
    RESTORE_NOTE="pg_restore 返回非 0（自定义格式恢复常有非致命告警），告警 $(wc -l < "$RESTORE_LOG") 行"
    head -5 "$RESTORE_LOG"
fi
echo "$RESTORE_NOTE"

# ---------- 指纹比对 ----------
bash "$PLAT/scripts/migration/recon.sh" "$PROD_CONTAINER" "$PROD_DB" > "$WORK/prod.tsv"
bash "$PLAT/scripts/migration/recon.sh" "$DRILL_CONTAINER" "$DRILL_DB" > "$WORK/drill.tsv"
cp "$WORK/prod.tsv" "$REPORT_DIR/A0-recon-prod_${TS}.tsv"
cp "$WORK/drill.tsv" "$REPORT_DIR/A0-recon-drill_${TS}.tsv"
diff "$WORK/prod.tsv" "$WORK/drill.tsv" > "$WORK/recon.diff" || true

TOTAL_KEYS=$(wc -l < "$WORK/prod.tsv")
# 关键指纹：内容 md5 + 金额合计 + 核销/平衡不变量
CRIT_RE='^(md5\||sum\||count\|)'
CRIT_DIFF=$(grep -E "^[<>] $CRIT_RE" "$WORK/recon.diff" | grep -c . || true)
ROWS_DIFF=$(grep -E '^[<>] [a-z_]+\.[a-z_0-9]+' "$WORK/recon.diff" | grep -c . || true)

# ---------- 附件（filestore）比对：全量，不抽样 ----------
# store_fname 本身就是相对 filestore/<db> 的路径（形如 "44/44d16...ba7"），直接当路径用。
# 缺失必须分两类计：备份缺而生产有 = 备份缺陷（FAIL）；生产本身就没有 = 现网既有问题（记已知问题）。
FS_RESULT="跳过（无 filestore 备份）"
FS_FAIL=0
ORPHAN_NOTE=""
MISS_BACKUP=0; MISS_PROD=0; DEFECT=0; SRC_N=0; DST_N=0; DB_REF=0
if [ -n "$FS_TAR" ]; then
    tar -xzf "$FS_TAR" -C "$WORK"
    find "$PLAT/data/odoo/filestore/$PROD_DB" -type f -printf '%P\n' | sort > "$WORK/prod_files.txt"
    find "$WORK/filestore/$PROD_DB"                 -type f -printf '%P\n' | sort > "$WORK/bak_files.txt"
    docker exec "$DRILL_CONTAINER" psql -U odoo -d "$DRILL_DB" -Atc \
        "select distinct store_fname from ir_attachment
          where store_fname is not null and store_fname<>'' order by 1" > "$WORK/db_files.txt"
    comm -23 "$WORK/db_files.txt" "$WORK/bak_files.txt"  > "$WORK/miss_in_backup.txt"
    comm -23 "$WORK/db_files.txt" "$WORK/prod_files.txt" > "$WORK/miss_in_prod.txt"
    # 备份缺陷 = 在备份里缺、但在生产里存在的文件
    comm -23 "$WORK/miss_in_backup.txt" "$WORK/miss_in_prod.txt" > "$WORK/backup_defect.txt"
    MISS_BACKUP=$(wc -l < "$WORK/miss_in_backup.txt")
    MISS_PROD=$(wc -l < "$WORK/miss_in_prod.txt")
    DEFECT=$(wc -l < "$WORK/backup_defect.txt")
    SRC_N=$(wc -l < "$WORK/prod_files.txt")
    DST_N=$(wc -l < "$WORK/bak_files.txt")
    DB_REF=$(wc -l < "$WORK/db_files.txt")
    # 备份里有、但恢复库不再引用的文件（只会是演练窗口内生产新写入，不影响可用性）
    ORPHAN=$(comm -13 "$WORK/db_files.txt" "$WORK/bak_files.txt" | wc -l)
    # 抽样内容指纹：证明"文件存在"且"字节可读"
    SAMPLE_MD5=$(head -200 "$WORK/db_files.txt" | while IFS= read -r f; do
            p="$WORK/filestore/$PROD_DB/$f"; [ -f "$p" ] && md5sum "$p" | cut -d' ' -f1
        done | md5sum | cut -d' ' -f1)
    FS_RESULT="DB 引用附件 $DB_REF 个（27564 行附件记录去重后）；生产 filestore $SRC_N 个文件 / 备份解包 $DST_N 个；\
备份缺 $MISS_BACKUP 个，其中生产本身也缺 $MISS_PROD 个 → **真正的备份缺陷 $DEFECT 个**；备份内未被引用 $ORPHAN 个；抽样 200 个内容 md5 聚合=$SAMPLE_MD5"
    echo "$FS_RESULT"
    [ "$DEFECT" -eq 0 ] || { echo "FAIL: $DEFECT 个附件在备份中缺失而生产存在"; FS_FAIL=$((FS_FAIL + 1)); }
    [ "$SRC_N" -eq "$DST_N" ] || { echo "FAIL: filestore 文件数不一致（$SRC_N vs $DST_N）"; FS_FAIL=$((FS_FAIL + 1)); }
    if [ "$MISS_PROD" -gt 0 ]; then
        cp "$WORK/miss_in_prod.txt" "$REPORT_DIR/A0-filestore现网缺失_${TS}.txt"
        # 用 VALUES 内联缺失清单，在恢复库里查这些附件的归属模型（判断是否影响业务证据）
        VALUES=$(sed "s|.*|('\0')|" "$WORK/miss_in_prod.txt" | paste -sd, -)
        docker exec "$DRILL_CONTAINER" psql -U odoo -d "$DRILL_DB" -Atc \
            "select coalesce(res_model,'(null)') as model, count(*) as n
              from ir_attachment where store_fname in (values $VALUES)
              group by 1 order by 2 desc" > "$WORK/resmodel.txt"
        echo "WARN: 现网 filestore 自身缺 $MISS_PROD 个附件文件（既有数据问题，非本次备份缺陷）；归属模型分布："
        sed 's/^/      /' "$WORK/resmodel.txt" || true
        cp "$WORK/resmodel.txt" "$REPORT_DIR/A0-filestore缺失归属_${TS}.txt" 2>/dev/null || true
    fi
    ORPHAN_NOTE="$ORPHAN"
fi

VERDICT="PASS"
[ "$CRIT_DIFF" -eq 0 ] || VERDICT="FAIL"
[ "$FS_FAIL" -eq 0 ] || VERDICT="FAIL"
[ -s "$WORK/recon.diff" ] || ROWS_DIFF=0

{ cat <<EOF
# A0 备份恢复演练报告 $TS

| 项 | 值 |
|---|---|
| 结论 | **$VERDICT** |
| 数据库备份 | \`$(basename "$DB_DUMP")\`（$(du -h "$DB_DUMP" | cut -f1)） |
| filestore 备份 | \`${FS_TAR:-无}\` |
| 恢复方式 | \`gunzip -c \| pg_restore --no-owner --role=odoo\` 到新库 \`$DRILL_DB\`（一次性容器 \`$DRILL_CONTAINER\`，演练后删除） |
| 恢复告警 | $RESTORE_NOTE |
| 指纹条目数 | $TOTAL_KEYS（逐表行数 + 金额/不变量 + 内容 md5） |
| **关键指纹差异**（md5\|/sum\|/count\|） | **$CRIT_DIFF**（判据：必须为 0） |
| 逐表行数差异 | $ROWS_DIFF（备份时刻与演练时刻之间的在线写入，A1 平桥冻结后应为 0） |
| filestore 完整性 | DB 引用 $DB_REF 个去重文件；生产 $SRC_N / 备份 $DST_N；备份缺陷 **$DEFECT**；现网自身缺失 $MISS_PROD（既有问题） |
| 附件演练 | $FS_RESULT |

产物：\`A0-recon-prod_${TS}.tsv\` / \`A0-recon-drill_${TS}.tsv\`（同目录，可直接 diff 复算）。

## 逐表行数差异明细

\`\`\`
$(grep -E '^[<>] [a-z_]+\.[a-z_0-9]+' "$WORK/recon.diff" || echo "（无）")
\`\`\`

## 关键指纹差异明细

\`\`\`
$(grep -E "^[<>] $CRIT_RE" "$WORK/recon.diff" || echo "（无 —— 历史数据与金额完全一致）")
\`\`\`

## 判据说明

- 关键指纹（内容 md5、借贷合计、凭证平衡、核销 matching_number 一致性、partial 悬挂、加密字段密文/明文比例）
  任一差异都意味着"备份恢复出来的数据与生产不一致"，必须为 0。
- 逐表行数允许非 0：本演练不冻结生产写入，差异应全部落在在线业务/日志表；
  A1 平桥会先冻结 cron 与写入，届时两侧必须完全 0 差异。
EOF
} > "$REPORT"

echo "=== 结果 ==="
echo "指纹条目 $TOTAL_KEYS | 关键指纹差异 $CRIT_DIFF | 行数差异 $ROWS_DIFF | 附件失败 $FS_FAIL"
echo "报告: $REPORT"
[ "$VERDICT" = "PASS" ] || exit 2
