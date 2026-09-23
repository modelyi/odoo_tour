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
# 十条实测铁律（每条都是一次失败换来的，别改回旧写法）：
#  1. 只搬两侧都存在的列（information_schema 交集），再减去清单第 3 列的人工排除。
#  2. **列存在 ≠ 列可比**：必须比 `udt_name`。20 把一批字段改成 translatable（text→jsonb），
#     COPY 时报 `invalid input syntax for type json / Token "Events" is invalid`，
#     而列级 diff 完全看不出来（两边都有这个列名）。本脚本按类型自动加 `to_jsonb()` / `#>>'{}'`。
#  3. **`LIKE … EXCLUDING ALL` 挡不住 NOT NULL**（实测：`null value in column "tz" of relation
#     "__stg_hr_version"`）。PG 文档里 `EXCLUDING CONSTRAINTS` 只管 CHECK 约束，NOT NULL 是列属性、
#     永远被 LIKE 复制。所以 staging 建完必须逐列 `DROP NOT NULL`，否则 19 的 NULL 在
#     **COPY 进 staging** 时就炸，报错点不在最终表上，极易误判成"目标表结构问题"。
#     目标侧 `GENERATED` 列直接从交集里剔掉（既不能插、也拦 NULL）。
#  4. **m2m 关系表没有 id 列**（`tour_plan_guide_rel` 只有 plan_id/guide_id）：
#     有 id 才走 ON CONFLICT (id) 与 setval，没 id 一律 ON CONFLICT DO NOTHING。
#  5. 顺序按外键拓扑、父在前；单表失败不中断整片（失败多半只是父表还没搬，
#     一次跑完才能看到全貌 —— 一遇错就中断反而看不清）。
#  6. **列标识符一律双引号**：`mail_message_subtype.default`、`ir_act_window.limit` 这类保留字
#     列名，裸写报的是 `syntax error at or near "default"`，表现成"少了 17 行"的假数据问题。
#  7. **同 id ≠ 同一条记录**：`utm_source` / `ir_model` / `account_tax` 这类"模块基数据"，
#     19 和 20 各自装模块时都建了一份，名字相同、id 不同（实测 `utm_source(Facebook)` 撞唯一键、
#     `crm_lead.source_id=15` 在 20 不存在 → 80 条线索全落不进去）。这类外键**必须按自然键重映射**。
#     机制：`remap/<表名>.txt`，`@ref 源表 键列` 把 19 的 (id, 键) 镜像成目标库的 `__ref_源表`，
#     其余行是**在目标库**、COPY 之后 INSERT 之前对 `__stg_表` 执行的 UPDATE（此时两侧都在，
#     所以能在目标侧解析出正确 id —— 这也是为什么不能写在 SELECT 里：SELECT 跑在源库，看不到 20 的表）。
#  8. 单表失败时先问"是父表没搬（级联）还是本表脏"：级联不用管，重跑上层即可。
#  9. **"20 新增 NOT NULL 列"的兜底必须拼进 INSERT 列表，补 staging 是补不进去的**：
#     该列不在两侧交集里 → 进不了 collist → `INSERT … SELECT collist` 永远不带它。
#     于是那 15 处 fill UPDATE 全跑完、日志好看，最终仍报
#     `null value in column "zip_applicability"`（实测）。这类列按字面量插入；
#     外键类（造不出 id）直接判 FAIL 并点名列，不许悄悄 0 行蒙过去。
#  10. **"NULL 就删行"的兜底只能作用于交集列**：不在交集里的列在 staging 里恒为 NULL
#      （19 压根没有这一列），拿它当删行条件就是**把整表删空**。实测 res_partner_bank 97 行
#      全被这条 DELETE 吃掉，表现成"LESS-97 但不报 FAIL"，然后 account_journal → 27.6 万凭证
#      → 81.8 万分录整条链 0 行 —— 一个自伤把全链路堵死，查了 40 分钟才查到这里。
#      这类列的去留只由 fixcol / xbad 通道决定（见铁律 9），与 staging 无关。
set -u          # 故意不带 -e：见下方 rc 注释——每一步显式取退出码，
              # 靠 set -e 判定会在 if/子 shell 上下文里失效，造成**静默半搬迁**
LIST="${1:?用法: etl_slice.sh <清单文件> [库名]}"
DST_DB="${2:-s0tour}"
SRC_C=tms-db; SRC_DB=tms
DST_C=odoo20-db
RMDIR="$(dirname "$LIST")/remap"      # 外键 id 两侧不同 → 按自然键重映射
FIXDIR="$(dirname "$LIST")/fixcol"     # 19 没有的列 → 按可评审的 SQL 规则填值
TMPQ=$(mktemp -d /tmp/etl_slice.XXXX); trap 'rm -rf "$TMPQ"' EXIT

cols_sql() {  # $1=容器 $2=库 $3=表 → "列名|udt"，按列名排序；$4=1 时剔掉 GENERATED 列（目标侧）
  docker exec "$1" psql -U odoo -d "$2" -At -F'|' -c \
    "select column_name, udt_name from information_schema.columns
      where table_schema='public' and table_name='$3'
        and ('${4:-0}'='0' or is_generated='NEVER')" | sort -t'|' -k1,1
}

OKC=0; BAD=0; FAILED=""
FILLLOG="${FILLLOG:-/tmp/b0/etl_fill.tsv}"; touch "$FILLLOG"   # 追加不截断：两轮跑要合看
# 清单一次性读进数组，**不要 `while read … done < 文件`**：循环体里有 `docker exec -i`
# （COPY FROM STDIN）和若干子进程，它们会分走 fd0 —— 实测第一张表跑完就读到 EOF，
# 117 表的清单只跑了 1 表还不报错（"完成：OK=1"），是典型的静默少搬。
mapfile -t LINES < "$LIST"
for line in "${LINES[@]}"; do
  read -r mode tbl EXCLUDE <<< "$line"
  case "${mode:-}" in ''|'#'*|skip*) continue ;; esac
  jf="$TMPQ/$tbl.jf"
  join -t'|' <(cols_sql "$SRC_C" "$SRC_DB" "$tbl") <(cols_sql "$DST_C" "$DST_DB" "$tbl" 1) > "$TMPQ/$tbl.j"
  if [ -n "${EXCLUDE:-}" ]; then
    awk -F'|' -v x="$(tr 'A-Z' 'a-z' <<<"$EXCLUDE")" \
      'BEGIN{n=split(x,a,",");for(i=1;i<=n;i++)d[a[i]]=1} !($1 in d)' "$TMPQ/$tbl.j" > "$jf"
  else cp "$TMPQ/$tbl.j" "$jf"; fi
  # **所有列标识符一律加双引号**：`mail_message_subtype` 有一列就叫 `default`，
  # 裸写 → `syntax error at or near "default"` + `DEFAULT is not allowed in this context`，
  # 表现成"这行少了 17 条"这种假数据问题，极难往保留字上想。
  collist=$(awk -F'|' '{printf "%s\"%s\"", sep, $1; sep=", "}' "$jf")
  if [ -z "$collist" ]; then
    echo "SKIP          $tbl  两侧无公共列"; BAD=$((BAD+1)); FAILED="$FAILED $tbl"; continue
  fi
  hasid=$(awk -F'|' '$1=="id"{f=1} END{print f?"yes":"no"}' "$jf")
  # 注意：awk 程序整体在单引号里，**不能再写单引号字面量**（会提前闭合，报 syntax error）；
  # 需要 SQL 的单引号一律用 -v Q="'" 传进来拼。字符串与变量拼接用**空格**，不要写 `&`
  # （`&` 是 awk 的按位与，mawk 直接报 syntax error —— 本脚本第一版中过一次）。
  sel=$(awk -F'|' -v Q="'" '{ c=$1; s=$2; t=$3; C="\"" c "\"";
         if (s==t)                       e=C;
         else if (t=="jsonb"||t=="json") e="to_jsonb(cast(" C " as text))";
         else if (s=="jsonb"||s=="json") e="(case when jsonb_typeof(" C ")=" Q "string" Q " then " C "#>>" Q "{}" Q " else " C "::text end)";
         else                            e="cast(" C " as " t ")";
         printf "%s%s as \"%s\"", sep, e, c; sep=", " }' "$jf")

  # staging 建完把 NOT NULL 全剥掉（见铁律 3）； GENERATED 列已在交集阶段剔除
  nn=$(docker exec "$DST_C" psql -U odoo -d "$DST_DB" -At -c \
    "select coalesce(string_agg('alter column \"' || a.attname || '\" drop not null', ', '), '')
       from pg_attribute a join pg_class c on c.oid = a.attrelid
      where c.relname = '$tbl' and c.relnamespace = 'public'::regnamespace
        and a.attnum > 0 and not a.attisdropped
        and a.attnotnull and a.attgenerated = ''") || nn=""
  [ -n "$nn" ] || nn=""
  [ -n "$nn" ] && nn="alter table __stg_$tbl $nn;"

  # 20 **新增的 NOT NULL 列**在 19 根本没有对应数据（列不在交集里 → staging 为 NULL →
  # 最终 INSERT 违约）。实测撞了 11 张表：res_company.inventory_period / account_move.review_state /
  # sale_order.document_tax_mode / res_partner_bank.clearing_label_id / hr_version.tz /
  # res_country.zip_applicability / website.header_search_type / payment_method.provider_id /
  # account_reconcile_model.payment_tolerance_type / resource_calendar.calendar_type /
  # sms_template.model_id。规则：有 DB 默认用 DB 默认；否则按类型兜底（文本→''、数值→0、
  # bool→false、jsonb→'null'）；**外键列无法凭空造 id → 删该行**（宁可少一行并留痕，
  # 也不要整表 0 行进不去）。每条动作都写进 $FILLLOG，B2 要拿这张清单逐列找业务定值。
  fills=$(docker exec "$DST_C" psql -U odoo -d "$DST_DB" -At -F$'\t' -c "
    select a.attname,
           case when fk.o is not null and nullif(pg_get_expr(d.adbin, d.adrelid), '') is null
                     then 'drop'
                when coalesce(nullif(pg_get_expr(d.adbin, d.adrelid), ''), fb.expr) is null
                     then 'none'
                else 'fill'
           end,
           coalesce(nullif(pg_get_expr(d.adbin, d.adrelid), ''), fb.expr, '')
      from pg_attribute a
      join pg_class c   on c.oid = a.attrelid and c.relnamespace = 'public'::regnamespace
      join pg_type t    on t.oid = a.atttypid
      left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
      left join lateral (select min(k.oid) o from pg_constraint k
                          where k.contype = 'f' and k.conrelid = a.attrelid and a.attnum = any (k.conkey)) fk on true
      left join lateral (select case t.typname
                                  when 'varchar'  then quote_literal('')
                                  when 'text'     then quote_literal('')
                                  when 'name'     then quote_literal('')
                                  when 'bool'     then 'false'
                                  when 'int2'     then '0'
                                  when 'int4'     then '0'
                                  when 'int8'     then '0'
                                  when 'numeric'  then '0'
                                  when 'float4'   then '0'
                                  when 'float8'   then '0'
                                  when 'jsonb'    then quote_literal('null') || '::jsonb'
                                  else null
                                end expr) fb on true
     where a.attrelid = '$tbl'::regclass and a.attnum > 0 and not a.attisdropped
       and a.attnotnull and a.attgenerated = ''
     order by a.attnum")
  # 逐列求值会退化成"每个 NOT NULL 列一次全表扫"（account_move 有 30+ 个），所以合成两条语句：
  # 一条 UPDATE 补默认、一条 DELETE 掉无法造 id 的行。
  # **只允许作用于交集列**：不在交集里的列 staging 恒为 NULL（19 根本没有这列），
  # 若按 `col is null` 删行就等于**把整表删空** —— 实测 res_partner_bank 97 行全被删掉，
  # 表现为"LESS-97 但不报 FAIL"，然后 account_journal→凭证→分录整条链 0 行，
  # 一路查了 40 分钟才查到这里。这类列的去留由下面的 fixcol / xbad 通道决定，与 staging 无关。
  fillsql=$(awk -F'\t' -v T="$tbl" -v JF="$jf" '
      BEGIN{while((getline l<JF)>0){split(l,p,"|");h[p[1]]=1}}
      !($1 in h) { next }
      $2=="fill" { if (u == "") { u = "set " } else { u = u ", "; w = w " or " }
                   u = u "\"" $1 "\" = coalesce(\"" $1 "\", " $3 ")"; w = w "\"" $1 "\" is null" }
      $2=="drop" { if (d != "") d = d " or "; d = d "\"" $1 "\" is null" }
      END {
        if (u != "") printf "update __stg_%s %s where %s;\n", T, u, w;
        if (d != "") printf "delete from __stg_%s where %s;\n", T, d;
      }' <<< "$fills")
  fillinv=$(awk -F'\t' -v T="$tbl" '{ printf "%s\t%s\t%s\n", T, $1, ($2=="fill" ? "补默认" : ($2=="drop" ? "drop-行" : "no-fallback")) }' <<<"$fills")

  # **补 staging 救不了"列根本不在交集里"的情况**：20 新增的 NOT NULL 列在 19 不存在 →
  # 它进不了 collist → 最终 `INSERT INTO t (collist) SELECT collist FROM __stg` 压根不带这列，
  # 于是 UPDATE 了个寂寞，仍然违约（实测 res_country.zip_applicability 被判成 FAIL(INSERT)，
  # 而 fill 日志里"补默认"数还挺好看）。这类列必须作为**字面量拼进 INSERT 列表**。
  # 同一列若在交集里（19 有、只是值为 NULL）则仍走上面的 staging UPDATE。
  # **规则填列（`fixcol/<表>.txt`）**：19 根本没有的列，取值必须来自一条**写进仓库、可评审**的
  # SQL 规则，而不是脚本凭类型猜。为什么必须有这个通道：20 有一类列**可空但带 CHECK** ——
  # 实测 `account_move_check_document_tax_mode_set` 要求发票类凭证的 document_tax_mode 非空，
  # 而上面的 fills 查询只看 `attnotnull`，这类列对脚本完全隐形 → 27.6 万条凭证一条都进不去。
  # 规则表达式里用 `s.` 引用 staging 行（staging 在 INSERT 里别名就是 s），所以可以按行取值。
  rules=""
  [ -f "$FIXDIR/$tbl.txt" ] && rules=$(awk -F'\t' '!/^#/ && NF>=2 {printf "%s\t%s\n", $1, $2}' "$FIXDIR/$tbl.txt")
  xfill=$(awk -F'\t' -v JF="$jf" -v R="$rules" '
      BEGIN{while((getline l<JF)>0){split(l,p,"|");h[p[1]]=1}
            n=split(R,rr,"\n"); for(i=1;i<=n;i++){split(rr[i],q,"\t"); if(q[1]!="")r[q[1]]=1}}
      !($1 in h) && !($1 in r) && $2=="fill"{printf "%s%s\t%s\n", sep, $1, $3; sep="\n"}' <<<"$fills")
  xbad=$(awk -F'\t' -v JF="$jf" -v R="$rules" '
      BEGIN{while((getline l<JF)>0){split(l,p,"|");h[p[1]]=1}
            n=split(R,rr,"\n"); for(i=1;i<=n;i++){split(rr[i],q,"\t"); if(q[1]!="")r[q[1]]=1}}
      !($1 in h) && !($1 in r) && $2!="fill"{printf "%s ", $1}' <<<"$fills")
  xc=""; xs=""
  if [ -n "$xfill" ]; then
    while IFS=$'\t' read -r cn cv; do
      [ -z "$cn" ] && continue
      xc="$xc, \"$cn\""; xs="$xs, $cv"
      printf '%s\t%s\t%s\n' "$tbl" "$cn" "补默认(字面量)" >> "$FILLLOG"
    done <<< "$xfill"
  fi
  if [ -n "$rules" ]; then
    while IFS=$'\t' read -r cn cv; do
      [ -z "$cn" ] && continue
      if grep -q "^$cn|" "$jf"; then
        echo "    !! $tbl.$cn 在 19 有值，规则填列不适用（改写成 remap/$tbl.txt 的 UPDATE）"
        continue
      fi
      xc="$xc, \"$cn\""; xs="$xs, ($cv)"
      printf '%s\t%s\t%s\n' "$tbl" "$cn" "规则填列(fixcol)" >> "$FILLLOG"
    done <<< "$rules"
  fi

  # ON CONFLICT 目标：有 id 才按 id 更新；insertignore / wipe / 无 id 一律 DO NOTHING
  conflict="DO NOTHING"
  if [ "$mode" = upsert ] && [ "$hasid" = yes ]; then
    conflict="(id) DO UPDATE SET $(awk -F'|' '$1!="id"{printf "%s\"%s\" = EXCLUDED.\"%s\"", sep, $1, $1; sep=", "}' "$jf")"
  fi
  pre=""; [ "$mode" = wipe ] && [ "$hasid" = yes ] && \
    pre="DELETE FROM $tbl WHERE id IN (SELECT id FROM __stg_$tbl);"

  # **不能靠 `if ! ( set -e … )` 判定成败**：bash 的规则是"-e 在 if/&& 上下文里被忽略时，
  # 该上下文内部的命令即使重设 set -e 也不再生效"。实测 res_country 的 INSERT 报
  # `null value in column "zip_applicability"`，但子 shell 退出码由最后一条 DROP TABLE 决定 →
  # 判成 OK，行数还正好相等（20 本来就有这 251 行）—— 这是最坏的一种失败：**静默半搬迁**。
  # 所以每一步显式取退出码，管道用 PIPESTATUS，错误文本收进 $LERR 只在失败时回显。
  S1=$(date +%s); LERR="$TMPQ/$tbl.err"; : > "$LERR"; rc=0; why=""
  docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
    -c "DROP TABLE IF EXISTS __stg_$tbl;
        CREATE TABLE __stg_$tbl (LIKE $tbl EXCLUDING ALL INCLUDING DEFAULTS);
        $nn
        do \$\$ declare n int; begin
          select count(*) into n from pg_attribute
           where attrelid = '__stg_$tbl'::regclass and attnum > 0 and not attisdropped
             and attnotnull and attgenerated = '';
          if n > 0 then raise exception 'staging 仍有 % 列 NOT NULL —— DROP NOT NULL 没生效', n; end if;
        end \$\$" 2>>"$LERR" || { rc=1; why=建表; }
  if [ "$rc" = 0 ]; then
    docker exec "$SRC_C" psql -U odoo -d "$SRC_DB" -q -v ON_ERROR_STOP=1 \
      -c "COPY (SELECT $sel FROM $tbl) TO STDOUT WITH (FORMAT text)" 2>>"$LERR" \
    | docker exec -i "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
      -c "COPY __stg_$tbl ($collist) FROM STDIN WITH (FORMAT text)" 2>>"$LERR"
    # 必须先把 PIPESTATUS 整个快照成标量再判定：`[ "${PIPESTATUS[0]}" = 0 ] && [ "${PIPESTATUS[1]}" = 0 ]`
    # 是错的 —— 第一个 [ ] 本身就是新管道，会把 PIPESTATUS 重置成 1 个元素，
    # 于是 [1] 在 set -u 下直接 unbound（实测 line 179 报错）。
    ps="${PIPESTATUS[*]}"; set -- $ps
    [ "$1" = 0 ] && [ "$2" = 0 ] || { rc=1; why=COPY; }
  fi
  if [ "$rc" = 0 ] && [ -f "$RMDIR/$tbl.txt" ]; then
    while IFS= read -r rl; do
      case "$rl" in
        ''|\#*) continue ;;
        @ref*)  read -r _ ra1 ra2 <<< "$rl"
                docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
                  -c "DROP TABLE IF EXISTS __ref_$ra1; CREATE TABLE __ref_$ra1 (id bigint, key text)" 2>>"$LERR" \
                  || { rc=1; why="ref $ra1 建表"; }
                docker exec "$SRC_C" psql -U odoo -d "$SRC_DB" -q -v ON_ERROR_STOP=1 \
                  -c "COPY (SELECT id, $ra2::text FROM $ra1) TO STDOUT" 2>>"$LERR" \
                | docker exec -i "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 \
                  -c "COPY __ref_$ra1 FROM STDIN" 2>>"$LERR"
                ps="${PIPESTATUS[*]}"; set -- $ps
                [ "$1" = 0 ] && [ "$2" = 0 ] || { rc=1; why="ref $ra1"; }
                echo "    ref  __ref_$ra1($ra2)" ;;
        *)      docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 -c "$rl" 2>>"$LERR" \
                  || { rc=1; why=重映射; } ;;
      esac
    done < "$RMDIR/$tbl.txt"
  fi
  if [ "$rc" = 0 ] && [ -n "$fillsql" ]; then
    while IFS= read -r fs; do
      [ -z "$fs" ] && continue
      docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 -c "$fs" 2>>"$LERR" \
        || { rc=1; why=补默认; }
    done <<< "$fillsql"
  fi
  [ -n "$fillinv" ] && printf '%s\n' "$fillinv" >> "$FILLLOG"
  if [ "$rc" = 0 ] && [ -n "$xbad" ]; then
    echo "FAIL          $tbl  (20 新增 NOT NULL 列无兜底，且 19 无此列: $xbad)"
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -c "DROP TABLE IF EXISTS __stg_$tbl" >/dev/null 2>&1 || :
    FAILED="$FAILED $tbl"; BAD=$((BAD+1)); continue
  fi
  if [ "$rc" = 0 ]; then
    docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -v ON_ERROR_STOP=1 -c "
      $pre INSERT INTO $tbl ($collist$xc) SELECT $collist$xs FROM __stg_$tbl s ON CONFLICT $conflict" 2>>"$LERR" \
      || { rc=1; why=INSERT; }
  fi
  docker exec "$DST_C" psql -U odoo -d "$DST_DB" -q -c "DROP TABLE IF EXISTS __stg_$tbl" >/dev/null 2>&1 || :
  if [ "$rc" != 0 ]; then
    echo "FAIL          $tbl  ($why)"
    sed 's/^/              /' "$LERR" | head -4
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
  # 两个计数都取到才允许判定（取空值时 "等于"会成立 → 假 OK）
  if ! [[ "$s" =~ ^[0-9]+$ && "$n" =~ ^[0-9]+$ ]]; then
    echo "FAIL          $tbl  (行数取不到 src=$s dst=$n)"; FAILED="$FAILED $tbl"; BAD=$((BAD+1)); continue
  fi
  if [ "$n" = "$s" ]; then tag=OK; OKC=$((OKC+1))
  elif [ "$n" -gt "$s" ]; then tag="MORE+$((n-s))（目标多出：20 基数据 或 违约行被 DO NOTHING 吃掉）"; BAD=$((BAD+1)); FAILED="$FAILED $tbl"
  else tag="LESS-$((s-n))（**缺行必须查**）"; BAD=$((BAD+1)); FAILED="$FAILED $tbl"; fi
  printf '%-12s %-34s src=%-8s dst=%-8s cols=%-4s %3ss  %s\n' "$mode" "$tbl" "$s" "$n" \
    "$(tr ',' '\n' <<<"$collist" | wc -l)" "$((S2-S1))" "$tag"
done
echo "== 完成：OK=$OKC  待定性=$BAD =="
[ -n "$FAILED" ] && echo "逐个定性:$FAILED"
# 20 新增 NOT NULL 列的填值台账（B2 要逐列找业务定值；no-fallback = 无 DB 默认也无类型兜底 → 必须人给）
if [ -s "$FILLLOG" ]; then
  echo "-- 补默认列: $(awk -F'\t' '$3=="补默认"' "$FILLLOG" | wc -l) 处 / 因 NULL 删行: $(awk -F'\t' '$3=="drop-行"' "$FILLLOG" | wc -l) 处 / 无兜底: $(awk -F'\t' '$3=="no-fallback"' "$FILLLOG" | wc -l) 处 → $FILLLOG"
  awk -F'\t' '$3=="no-fallback"{printf "  无兜底: %s.%s\n", $1, $2}' "$FILLLOG" | sort -u | head -20
fi
exit 0
