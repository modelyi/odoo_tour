#!/bin/bash
# S0 影子库的一轮完整重建（幂等；改完管线就从这里重跑）。
#
#   ./etl_s0_rebuild.sh [库名]     默认 s0tour
#
# 步骤是**有次序意义**的，不能省：
#   建库（TEMPLATE 秒级）→ 摘环上外键 → 搬两轮（upsert 幂等，第二轮补第一轮因环剪断的行）
#   → 加回外键（这一步就是引用完整性校验，产出"真脏数据"清单）→ 汇总。
# 每轮日志与补值台账留在 LOGDIR，对账报告直接从这里取数。
set -u
MIG=$(cd "$(dirname "$0")" && pwd)
DB=${1:-s0tour}
LOGDIR=${LOGDIR:-/tmp/b0}
LIST=${LIST:-$MIG/slices/s0_full.txt}
CYC=${CYC:-$MIG/slices/cycles.txt}
mkdir -p "$LOGDIR"
# 清单每次都重算：它是 seeds/modes/exclude 三个输入的函数，手维护必然出现
# "改了 exclude 忘了重生成"（实测 project_project alias_id 就这么漏了一次）。
# 放在建库之前只是不想查一个正在被 drop 的库 —— 模板库同构，前后等价。
if [ "${REGEN:-1}" = 1 ]; then
  echo "===== 重算清单 $(date -Is)"
  ./etl_make_list.sh "$DB" || { echo "清单生成失败（不带着旧清单继续跑）"; exit 1; }
fi
echo "===== 建库 $DB $(date -Is)"
docker exec odoo20-db psql -U odoo -d postgres -q \
  -c "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB OWNER odoo TEMPLATE ${TEMPLATE:-b1gate8}" \
  > "$LOGDIR/createdb.log" 2>&1 || { echo "建库失败："; cat "$LOGDIR/createdb.log"; exit 1; }
rm -f "$LOGDIR/etl_fill.tsv"
cd "$MIG" || exit 1
echo "===== 摘环上外键 $(date -Is)"
bash etl_cycle.sh drop "$CYC" "$DB" 2>&1 | tail -3
for p in 1 2; do
  echo "===== PASS $p $(date -Is)"
  FILLLOG="$LOGDIR/etl_fill.tsv" bash etl_slice.sh "$LIST" "$DB" > "$LOGDIR/rebuild_p$p.log" 2>&1
  echo "pass $p: OK=$(grep -c ' OK$' "$LOGDIR/rebuild_p$p.log")  FAIL=$(grep -c '^FAIL' "$LOGDIR/rebuild_p$p.log")"
done
echo "===== 加回外键（= 引用完整性校验）$(date -Is)"
bash etl_cycle.sh add "$CYC" "$DB" 2>&1 | tail -30
echo "===== 完成 $(date -Is)"
