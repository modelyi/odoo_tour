#!/bin/bash
# 19 → 20 单表搬运（S0 影子实例的第一块砖；S2 的增量重放复用同一套代码）。
#
#   ./etl_slice.sh <清单文件> [库名]        库名默认 s0tour
#
# 清单每行：`模式  表名  [人工排除列,逗号分隔]`
#   upsert        INSERT … ON CONFLICT (id) DO UPDATE —— 默认推荐。
#                 **不删目标行**：20 装载时模块自己造的基数据（国家、单位、科目模板…）
#                 与 19 同 id 的被覆盖、多出来的保留。影子库的干净做法是整库从模板重来
#                 （`CREATE DATABASE s0tour TEMPLATE b1gate8`，秒级），不是靠删。
#   insertignore  ON CONFLICT DO NOTHING —— 有业务唯一键、且**源侧本身就有违约行**的表用这个
#                 （ir_config_parameter / fleet_vehicle / tour_bank_account，见 TDS-32 §6 规则 4b）。
#   wipe          先按 id 删再插 —— 只在"19 绝对权威且目标侧可能被手改脏"时用，
#                 且必须**子表在前**，否则 DELETE 会被外键挡。
#
# 五条实测铁律（每条都是一次失败换来的，别改回旧写法）：
#  1. 只搬两侧都存在的列（information_schema 交集），再减去清单第 3 列的人工排除。
#  2. **列存在 ≠ 列可比**：必须比 `udt_name`。20 把一批字段改成 translatable（text→jsonb），
#     COPY 时报 `invalid input syntax for type json / Token "Events" is invalid`，
#     而列级 diff 完全看不出来（两边都有这个列名）。本脚本按类型自动加 `to_jsonb()` / `#>>'{}'`。
#  3. staging 表必须 `LIKE … EXCLUDING ALL INCLUDING DEFAULTS`：默认写法继承 NOT NULL，
#     于是 19 的 NULL 在 COPY **进 staging** 时就炸（`null value in column "zip_applicability"`），
#     报错点不在最终表上，极易误判成"目标表结构问题"。
#  4. **m2m 关系表没有 id 列**（`tour_plan_guide_rel` 只有 plan_id/guide_id）：
#     有 id 才走 ON CONFLICT (id) 与 setval，没 id 一律 ON CONFLICT DO NOTHING。
#  5. 顺序按外键拓扑、父在前；单表失败不中断整片（失败多半只是父表还没搬，
#     一次跑完才能看到全貌 —— 一遇错就中断反而看不清）。
set -eu
LIST="${1:?用法: etl_slice.sh <清单文件> [库名]}"
DST_DB="${2:-s0tour}"
SRC_C=tms-db; SRC_DB=tms
DST_C=odoo20-db
TMPQ=$(mktemp -d /tmp/etl_slice.XXXX); trap 'rm -rf "$TMPQ"' EXIT

cols_sql() {  # $1=容器 $2=库 $3=表 → "列名|udt"，按列名排序
  docker exec "$1" psql -U odoo -d "$2" -At -F'|' -c \
    "select column_name, udt_name from information_schema.columns
      where table_schema='public' and table_name='$3'" | sort -t'|' -k1,1
}

OKC=0; BAD=0; FAILED=""
while read -r mode tbl EXCLUDE; do
  case "${mode:-}" in ''|'#'*) continue ;; esac
  jf="$TMPQ/$tbl.jf"
  join -t'|' <(cols_sql "$SRC_C" "$SRC_DB" "$tbl") <(cols_sql "$DST_C" "$DST_DB" "$tbl") > "$TMPQ/$tbl.j"
  if [ -n "${EXCLUDE:-}" ]; then
    awk -F'|' -v x="$(tr 'A-Z' 'a-z' <<<"$EXCLUDE")" \
      'BEGIN{n=split(x,a,",");for(i=1;i<=n;i++)d[a[i]]=1} !($1 in d)' "$TMPQ/$tbl.j" > "$jf"
  else cp "$TMPQ/$tbl.j" "$jf"; fi
  collist=$(awk -F'|' '{printf "%s%s", sep, $1; sep=", "}' "$jf")
  if [ -z "$collist" ]; then
    echo "SKIP          $tbl  两侧无公共列"; BAD=$((BAD+1)); FAILED="$FAILED $tbl"; continue
  fi
  hasid=$(awk -F'|' '$1=="id"{f=1} END{print f?"yes":"no"}' "$jf")
  # 注意：awk 程序整体在单引号里，**不能再写单引号字面量**（会提前闭合，报 syntax error）；
  # 需要 SQL 的单引号一律用 -v Q="'" 传进来拼。
  sel=$(awk -F'|' -v Q="'" '{ c=$1; s=$2; t=$3;
      if (s==t)                       e=c;
      else if (t=="jsonb"||t=="json") e="to_jsonb(cast("&c" as text))";
      else if (s=="jsonb"||s=="json") e="(case when jsonb_typeof("&c")="Q"string"Q" then "&c"#>>"Q"{}"Q" else "&c"::text end)";
      else                            e="cast("&c" as "&t")";
      printf "%s%s as %s", sep, e, c; sep=", " }' "$jf")

  # ON CONFLICT 目标：有 id 才按 id 更新；insertignore / wipe / 无 id 一律 DO NOTHING
  conflict="DO NOTHING"
  if [ "$mode" = upsert ] && [ "$hasid" = yes ]; then
    conflict="(id) DO UPDATE SET $(awk -F'|' '$1!="id"{printf "%s%s = EXCLUDED.%s", sep, $1, $1; sep=", "}' "$jf")"
  fi
  pre=""; [ "$mode" = wipe ] && [ "$hasid" = yes ] && \
    pre="DELETE FROM $tbl WHERE id IN (SELECT id FROM __stg_$tbl);"

  S1=$(date +%s)
  if ! ( set -e
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
      -c "DROP TABLE IF EXISTS __stg_$tbl;
          CREATE TABLE __stg_$tbl (LIKE $tbl EXCLUDING ALL INCLUDING DEFAULTS)"
    docker exec "$SRC_C" psql -U odoo -d "$SRC_DB" -q -v ON_ERROR_STOP=1 \
      -c "COPY (SELECT $sel FROM $tbl) TO STDOUT WITH (FORMAT text)" \
    | docker exec -i "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
      -c "COPY __stg_$tbl ($collist) FROM STDIN WITH (FORMAT text)"
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 -c "
      $pre INSERT INTO $tbl ($collist) SELECT $collist FROM __stg_$tbl ON CONFLICT $conflict"
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -c "DROP TABLE __stg_$tbl"
  ); then
    echo "FAIL          $tbl"
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -c "DROP TABLE IF EXISTS __stg_$tbl" || :
    FAILED="$FAILED $tbl"; BAD=$((BAD+1)); continue
  fi
  if [ "$hasid" = yes ]; then
    mx=$(docker exec "$SRC_C" psql -U odoo -d "$SRC_DB" -At -c "select coalesce(max(id),1) from $tbl")
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -At -c \
      "select setval(pg_get_serial_sequence('$tbl','id'), $mx, true)" >/dev/null
  fi
  s=$(docker exec "$SRC_C" psql -U odoo -d "$SRC_DB" -At -c "select count(*) from $tbl")
  n=$(docker exec "$DST_C" psql -U odoo -d "$DST_DB" -At -c "select count(*) from $tbl")
  S2=$(date +%s)
  if [ "$n" = "$s" ]; then tag=OK; OKC=$((OKC+1))
  elif [ "$n" -gt "$s" ]; then tag="MORE+$((n-s))（目标多出：20 基数据 或 违约行被 DO NOTHING 吃掉）"; BAD=$((BAD+1)); FAILED="$FAILED $tbl"
  else tag="LESS-$((s-n))（**缺行必须查**）"; BAD=$((BAD+1)); FAILED="$FAILED $tbl"; fi
  printf '%-12s %-34s src=%-8s dst=%-8s cols=%-4s %3ss  %s\n' "$mode" "$tbl" "$s" "$n" \
    "$(tr ',' '\n' <<<"$collist" | wc -l)" "$((S2-S1))" "$tag"
done < "$LIST"
echo "== 完成：OK=$OKC  待定性=$BAD =="
[ -n "$FAILED" ] && echo "逐个定性:$FAILED"
exit 0
