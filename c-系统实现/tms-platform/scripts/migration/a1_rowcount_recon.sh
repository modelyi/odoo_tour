#!/bin/bash
# A1 一致性核对（第 1 项：逐表精确行数 0 差异）
#   源：tms-db / tms      目标：tour-db / tour19
# 两侧各跑一次 `count(*)` 全表，落成两份 "表名 行数" 再 diff。
# 只读，不写任何一侧。
set -u
OUT="${OUT:-/tmp/a1_recon}"
mkdir -p "$OUT"
gen() {  # $1=容器 $2=库名 $3=输出
  docker exec "$1" psql -U odoo -d "$2" -At -F' ' -c "
WITH t AS (SELECT schemaname||'.'||relname AS tbl
           FROM pg_stat_user_tables
           WHERE schemaname NOT IN ('pg_catalog','information_schema'))
SELECT string_agg('SELECT ''' || tbl || ''' t, (SELECT count(*) FROM ' || tbl || ') c',
                  ' UNION ALL ')
FROM t;" > "$OUT/$3.query"
  docker exec -i "$1" psql -U odoo -d "$2" -At -F' ' -f - < "$OUT/$3.query" > "$OUT/$3.counts" 2>"$OUT/$3.err"
  echo "$(basename $3) 表数=$(wc -l < $OUT/$3.counts)  err=$(wc -c < $OUT/$3.err)"
}
gen tms-db    tms     src
gen tour-db   tour19  dst
echo "---- 差异（空=0 差异）----"
diff <(sort "$OUT/src.counts") <(sort "$OUT/dst.counts") | head -60
echo "---- 汇总 ----"
echo "src 总行数=$(awk '{s+=$2} END{print s}' $OUT/src.counts)  dst 总行数=$(awk '{s+=$2} END{print s}' $OUT/dst.counts)"
