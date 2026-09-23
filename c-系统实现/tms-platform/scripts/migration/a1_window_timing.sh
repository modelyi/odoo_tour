#!/bin/bash
# A1 冻结窗口**计时**（对生产只读，不改 tms 一行、不动 nginx）。
# 目的：把"需要 4–6 小时窗口"从估计变成实测 —— 窗口长度是谈判冻结时段的唯一硬依据。
# 计时项 = 末次 dump → 重灌 → 复测三段的真实耗时；正式窗口里就是这三段 + 冒烟。
#   用法：bash a1_window_timing.sh            （新库 a1timing，跑完自己 drop）
#         KEEP=1 bash a1_window_timing.sh     （保留计时库）
set -eu
SRC_C=tms-db; SRC_DB=tms
DST_C=tour-db; DST_DB="${DST_DB:-a1timing}"
WORK="${WORK:-$HOME/mig_timing}"; mkdir -p "$WORK"
STAMP=$(date +%Y%m%d_%H%M%S)
DUMP="$WORK/tms_$STAMP.dump"
dur() { echo "$(( $2 - $1 ))s"; }

echo "== 0. 基线行数（dump 时刻的真相稍后由 recon 复测）=="
T0=$(date +%s)
docker exec "$SRC_C" psql -U odoo -d "$SRC_DB" -At -F'|' -c \
  "select count(*) from account_move_line" | sed 's/^/  account_move_line=/'

echo "== 1. pg_dump -Fc $SRC_DB（生产侧只读）=="
T1=$(date +%s)
# 注意：**不要写 `-f -`** —— 实测在 `docker exec` 下 `pg_dump -f -` 静默产出 0 字节且 rc=0，
# 会让"dump 成功"变成假绿（本脚本第一版就中过）。省略 -f 让它自然走 stdout。
docker exec "$SRC_C" pg_dump -U odoo -Fc -Z6 "$SRC_DB" > "$DUMP"
T2=$(date +%s)
SIZE=$(stat -c%s "$DUMP")
[ "$SIZE" -gt 1048576 ] || { echo "  dump 只有 $SIZE 字节 —— 判定失败，不进入计时"; exit 1; }
echo "  dump=$DUMP size=$((SIZE/1024/1024))MB 耗时=$(dur $T1 $T2)"

echo "== 2. 建库 + pg_restore --no-owner --role=odoo =="
T3=$(date +%s)
docker exec "$DST_C" psql -U odoo -d postgres -q -c "DROP DATABASE IF EXISTS $DST_DB"
docker exec "$DST_C" psql -U odoo -d postgres -q -c "CREATE DATABASE $DST_DB OWNER odoo"
# `pg_restore -j` **不能从 stdin 读**（实测 `parallel restore from standard input is not supported`），
# 所以必须先把 dump 送进容器再按文件恢复 —— 正式窗口里也是这个形态。
docker cp "$DUMP" "$DST_C":/tmp/restore_$STAMP.dump
docker exec "$DST_C" pg_restore -U odoo -d "$DST_DB" --no-owner --role=odoo \
  -j 4 --exit-on-error /tmp/restore_$STAMP.dump 2>"$WORK/restore_$STAMP.err" || {
    echo "  restore 失败，见 $WORK/restore_$STAMP.err"; tail -20 "$WORK/restore_$STAMP.err"; exit 1; }
T4=$(date +%s)
echo "  restore 耗时=$(dur $T3 $T4)  err 行数=$(wc -l < $WORK/restore_$STAMP.err)"

echo "== 3. 复测（关键表精确行数，两侧同刻不可得，故只判'目标不少于 dump 时点'）=="
docker exec "$DST_C" psql -U odoo -d "$DST_DB" -At -F'|' -c \
  "select 'account_move_line', count(*) from account_move_line
   union all select 'account_move', count(*) from account_move
   union all select 'tour_plan', count(*) from tour_plan
   union all select 'res_partner', count(*) from res_partner" | sed 's/^/  /'
T5=$(date +%s)

echo "== 4. ANALYZE（正式窗口不需要，副本自检用）=="
docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -c "ANALYZE" ; T6=$(date +%s)

echo "================ 计时汇总 ================"
printf '  dump(Z6)      %s\n  restore(j4)   %s\n  analyze       %s\n  合计          %s\n' \
  "$(dur $T1 $T2)" "$(dur $T3 $T4)" "$(dur $T5 $T6)" "$(dur $T1 $T6)"
echo "  ⇒ 冻结窗口 ≈ 合计 + 冒烟与签字（见 d-交付验收/B3-切换runbook_草案.md 的步骤号）"
[ "${KEEP:-0}" = "1" ] || docker exec "$DST_C" psql -U odoo -d postgres -q -c "DROP DATABASE $DST_DB"
docker exec "$DST_C" rm -f /tmp/restore_$STAMP.dump; rm -f "$DUMP"; echo "  计时库/文件已清理（KEEP=1 可保留）"
