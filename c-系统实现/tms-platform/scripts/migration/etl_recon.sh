#!/bin/bash
# S0/B2 对账报告：源库（19 tms）vs 影子库（20 s0tour）逐判据比对。
#
#   ./etl_recon.sh [目标库]        默认 s0tour
#
# 判据取自计划 §8 的不变式，全部是**可机器判定的 SQL**，不做人眼比对：
#   ① 逐账户借贷平衡（unbal_acct 必须两侧同为 0）
#   ② 全账本借贷合计  ③ 已过账凭证 amount_total 合计
#   ④ 核销号一致性：account_move_line.matching_number 必须恒等于 str(full_reconcile_id.id)
#      （这条只有在 20 侧保留了原 ID 时才可能成立 —— 它就是"象限 1 整表 INSERT"的验收判据）
#   ⑤ 核销残差（partial_reconcile 行数 + 两侧分录都非空的行数 + 被核销分录行数）
#      注：19/20 的 partial.reconcile 都是 debit_move_id / credit_move_id 两个 M2o，**没有** m2m 中间表
#          （计划 §8 里写的 account_move_line_partial_rel 在 19 不存在，实测纠正）
#   ⑥ 附件/元数据/序列/门户主数据行数
# 判据只看"两侧是否相等"：MORE 只允许出现在 20 自带基数据的表上，LESS 一律是缺陷。
# 退出码非 0 = 有差异，禁止签字。
set -u
SRC_C=tms-db; SRC_DB=tms
DST_C=odoo20-db; DST_DB=${1:-s0tour}

run() {  # $1=容器 $2=库 $3=SQL → "判据|值"
  docker exec "$1" psql -U odoo -d "$2" -At -F'|' -c "$3"
}

SQL="
select 'moves_posted',       count(*)::text from account_move where state='posted'
union all select 'aml_total',         count(*)::text from account_move_line
union all select 'aml_posted',        count(*)::text from account_move_line l join account_move m on m.id=l.move_id where m.state='posted'
union all select 'unbal_acct',        count(*)::text from (select l.account_id from account_move_line l join account_move m on m.id=l.move_id where m.state='posted' group by l.account_id having abs(sum(l.debit)-sum(l.credit))>0.005) x
union all select 'sum_debit_posted',  round(sum(l.debit)::numeric,2)::text from account_move_line l join account_move m on m.id=l.move_id where m.state='posted'
union all select 'sum_credit_posted', round(sum(l.credit)::numeric,2)::text from account_move_line l join account_move m on m.id=l.move_id where m.state='posted'
union all select 'sum_amount_total',  round(sum(amount_total)::numeric,2)::text from account_move where state='posted'
union all select 'matching_bad',      count(*)::text from account_move_line
      where full_reconcile_id is not null
        and matching_number is distinct from full_reconcile_id::text
union all select 'partial_reconcile', count(*)::text from account_partial_reconcile
union all select 'partial_two_side',  count(*)::text from account_partial_reconcile
      where debit_move_id is not null and credit_move_id is not null
union all select 'partial_sum_amount', round(sum(amount)::numeric,2)::text from account_partial_reconcile
union all select 'reconciled_aml',    count(*)::text from account_move_line where full_reconcile_id is not null
union all select 'analytic_line',     count(*)::text from account_analytic_line
union all select 'attachment',        count(*)::text from ir_attachment
union all select 'partner',           count(*)::text from res_partner
union all select 'users',             count(*)::text from res_users
union all select 'tour_plan',         count(*)::text from tour_plan
union all select 'tour_plan_account', count(*)::text from tour_plan_account
"
# 信息项（不计入差异）：matching_number 上有没有 DB 约束/索引。
# 实测两侧都**没有**唯一约束 —— 这条不变式是 ORM 级的，所以真正的判据只能靠上面的
# matching_bad=0（逐行回算），不要拿"约束存在"当过关。
J20="select coalesce(
        (select string_agg(conname, ',') from pg_constraint
          where conrelid='account_move_line'::regclass and conname like '%matching%'),
        '无约束')"
# 按设计**不搬**的表（etl_order.py 的 DENY / DENY_PREFIX）：20 装模块时会自建，
# 差异是预期的，但必须写在报告上，否则看的人会以为漏了。
DENY_SQL="select 'ir_model_data',   count(*)::text from ir_model_data
union all select 'ir_sequence',     count(*)::text from ir_sequence
union all select 'ir_config_param', count(*)::text from ir_config_parameter
union all select 'ir_cron',         count(*)::text from ir_cron"

F19=$(mktemp); F20=$(mktemp); trap 'rm -f "$F19" "$F20"' EXIT
run "$SRC_C" "$SRC_DB" "$SQL" > "$F19" || { echo "源库查询失败"; exit 1; }
run "$DST_C" "$DST_DB" "$SQL" > "$F20" || { echo "目标库查询失败"; exit 1; }

printf '%-20s %-17s %-17s %s\n' 判据 "19 (tms)" "20 ($DST_DB)" 判定
printf '%s\n' "------------------------------------------------------------------------------"
# 允许"只多不少"的判据：20 装模块自带基数据，目标侧必然 ≥ 源侧；
# 这类判据的反向（LESS）仍然算 DIFF。金额/平衡类判据一律要求**相等**。
GE="partner attachment"
BADD=0
while IFS='|' read -r k v19; do
  [ -n "$k" ] || continue
  v20=$(awk -F'|' -v K="$k" '$1==K{print $2; exit}' "$F20")
  if [ "$v19" = "${v20-}" ]; then j=OK
  elif [[ " $GE " == *" $k "* ]] && [ "$(python3 -c "print(int(float('${v20:-0}')>float('$v19')))")" = 1 ]; then
    j="OK(20 自带基数据，多 $((v20-v19)))"
  else j="DIFF"; BADD=$((BADD+1)); fi
  printf '%-20s %-17s %-17s %s\n' "$k" "$v19" "${v20:-<无此判据>}" "$j"
done < "$F19"

j20=$(run "$DST_C" "$DST_DB" "$J20")
printf '%-20s %-17s %-17s %s\n' "idx_matching" "-" "$j20" "信息项"

printf '%s\n' "------------------------------------------------------------------------------"
printf '%s\n'   "按设计不搬（20 侧自建基数据；差异是预期的，但必须留痕）"
run "$SRC_C" "$SRC_DB" "$DENY_SQL" > /tmp/recon_d19.txt
run "$DST_C" "$DST_DB" "$DENY_SQL" > /tmp/recon_d20.txt
while IFS='|' read -r k v19; do
  [ -n "$k" ] || continue
  v20=$(awk -F'|' -v K="$k" '$1==K{print $2; exit}' /tmp/recon_d20.txt)
  printf '%-20s %-17s %-17s %s\n' "$k" "$v19" "${v20:-<无>}" "不搬"
done < /tmp/recon_d19.txt
rm -f /tmp/recon_d19.txt /tmp/recon_d20.txt

printf '%s\n' "------------------------------------------------------------------------------"
echo "差异判据数: $BADD"
[ "$BADD" = 0 ] || exit 1
