#!/bin/bash
# 环上的外键：搬之前临时摘掉，搬完再加回来。
#
#   ./etl_cycle.sh drop [cycles.txt] [库名]     摘掉回边的外键，并把原始 DDL 存进 <cycles>.ddl
#   ./etl_cycle.sh add  [cycles.txt] [库名]     按存下来的 DDL 加回，**顺带做引用完整性校验**
#
# 为什么需要它（这一条是 27.6 万条凭证进不去的真正原因）：
# 拓扑排序只能决定"谁先插"，但 `INSERT … SELECT` 是**一条语句 = 一个事务**，
# 环上的表 account_move ↔ account_payment 互相引用，整表里只要有一条指向还没搬的行，
# **全部行都进不去**，跑几轮都不会收敛。摘掉外键才能两边都灌满，再加回来验证。
#
# `add` 失败不是事故，是**产出**：它精确指出哪一条 FK 指向的行真的不存在（真脏数据），
# 而"顺序问题"在这一层已经被完全排除掉了 —— 这正是 B2 对账要的东西。
set -u
DST_C=odoo20-db
SELF=$(cd "$(dirname "$0")" && pwd)
CYCLES=${2:-$SELF/slices/cycles.txt}
DST_DB=${3:-s0tour}
DDL="${CYCLES%.txt}.ddl"
ACT=${1:?用法: etl_cycle.sh drop|add [cycles.txt] [库名]}
[ -f "$CYCLES" ] || { echo "找不到 $CYCLES（先跑 etl_order.py）"; exit 2; }

psql_q() { docker exec "$DST_C" psql -U odoo -d "$DST_DB" -At -F'|' -c "$1"; }

if [ "$ACT" = drop ]; then
  : > "$DDL"; n=0; miss=0
  while read -r child parent; do
    case "$child" in ''|\#*) continue ;; esac
    rows=$(psql_q "select conname, pg_get_constraintdef(oid) from pg_constraint
                   where contype='f' and conrelid='$child'::regclass
                     and confrelid='$parent'::regclass order by conname")
    if [ -z "$rows" ]; then
      echo "  无外键    $child → $parent（20 侧已删该引用，跳过）"; miss=$((miss+1)); continue
    fi
    while IFS='|' read -r cname cdef; do
      [ -z "$cname" ] && continue
      psql_q "alter table $child drop constraint $cname" >/dev/null \
        || { echo "  !! 摘不掉 $child.$cname"; exit 3; }
      printf '%s\t%s\t%s\n' "$child" "$cname" "$cdef" >> "$DDL"
      echo "  摘除      $child.$cname  (→ $parent)"; n=$((n+1))
    done <<< "$rows"
  done < "$CYCLES"
  echo "== 已摘除 $n 条外键（记录在 $DDL）；20 侧本就无此引用的 $miss 对 =="
  exit 0
fi

if [ "$ACT" = add ]; then
  [ -s "$DDL" ] || { echo "没有 $DDL，先跑 drop"; exit 2; }
  ok=0; bad=0; BADLIST=""
  while IFS=$'\t' read -r child cname cdef; do
    [ -z "$cname" ] && continue
    # **判成败只能看退出码**：`psql -At -c "ALTER TABLE …"` 会把命令标签
    # "ALTER TABLE"打到 stdout，上一版把"有输出"当失败 → 218 条全被判成校验未过，
    # 而真正只有 5 条加不回去（都指向还没搬的 account_move）。噪声会淹没信号。
    err=$(docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
            -c "alter table $child add constraint $cname $cdef" 2>&1 >/dev/null)
    if [ -z "$err" ]; then
      ok=$((ok+1)); continue
    fi
    bad=$((bad+1)); BADLIST="$BADLIST $child.$cname"
    # 顺手把"到底有多少行悬空"算出来：PG 只报第一条违约行，对账要的是总量。
    col=$(printf '%s' "$cdef" | sed -n 's/^FOREIGN KEY ("\{0,1\}\([a-z_0-9]*\)"\{0,1\}).*/\1/p')
    par=$(printf '%s' "$cdef" | sed -n 's/^FOREIGN KEY ([^)]*) REFERENCES \(public\.\)\{0,1\}\([a-z_0-9]*\).*/\2/p')
    n=$(psql_q "select count(*) from $child c left join $par p on p.id = c.\"$col\"
                 where c.\"$col\" is not null and p.id is null" 2>/dev/null)
    echo "  !! 校验未过 $child.$cname  (列 $col → $par，悬空 ${n:-?} 行)"
  done < "$DDL"
  echo "== 加回 $ok 条；引用完整性未过 $bad 条（这些就是真脏数据，不是顺序问题）=="
  [ -n "$BADLIST" ] && echo "未过清单:$BADLIST" | tr ' ' '\n' | grep . | head -20
  exit 0
fi
echo "未知动作 $ACT（只支持 drop|add）"; exit 2
