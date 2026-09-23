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
-- 中间表（m2m）判据。**为什么单独列**：闭包靠"谁 FK 到谁"求传递闭包，而中间表是
-- 叶子 —— 没有任何表 FK 到它，所以父表全搬了它仍然可以是 0 行（实测：
-- account_move_line_account_tax_rel 4437→0、product_taxes_rel 233→0）。
-- 表现是"凭证金额都对，但税不见了"—— 逐表行数判据看不见这种缺口。
union all select 'jun_aml_tax',       count(*)::text from account_move_line_account_tax_rel
union all select 'jun_product_taxes', count(*)::text from product_taxes_rel
union all select 'jun_fp_tax',        count(*)::text from account_fiscal_position_account_tax_rel
union all select 'jun_account_company', count(*)::text from account_account_res_company_rel
union all select 'jun_company_users', count(*)::text from res_company_users_rel
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
# 附件判据。两个坑（本轮都实测踩过）：
#  ① 附件是**内容寻址**的：19 侧 27,564 行只对应 3,197 个文件（相同 checksum 共用一个
#     store_fname）→ "行数 = 文件数" 是错判据，会误报"丢了两万多个文件"。
#  ② 19 的 filestore 是**两个目录的并集**：主库 tms + 租户库 tms_tenant_1789530161
#     （实测 415 个对象只在租户目录里）。只拷 tms 目录 → 这 415 个附件在 20 上必 500。
#     B3 的 filestore 动作必须按并集做。
# 口径：**以源侧的文件清单为准**逐个查目标侧能否解析。20 自建行（资产包缓存
# ir.ui.view/*、装机头像）的缺失不算 —— 那些 20 会自己重建，混进来只会掩盖真问题。
FS19="/home/adai/tms/c-系统实现/tms-platform/data/odoo/filestore/tms
/home/adai/tms/c-系统实现/tms-platform/data/odoo/filestore/tms_tenant_1789530161"
FS20="/home/adai/odoo20/data/filestore/$DST_DB"
SFLIST=$(mktemp); trap 'rm -f "$F19" "$F20" "$SFLIST"' EXIT
run "$SRC_C" "$SRC_DB" \
  "select distinct store_fname from ir_attachment where store_fname is not null" | grep . > "$SFLIST"
# 空清单会让"缺失=0"变成假过关，必须先堵掉
[ -s "$SFLIST" ] || { echo "FAIL: 源侧附件清单为空（查询失败或无数据）"; exit 1; }
cnt_missing() {   # $1=filestore 根（可多个，换行/空白分隔）→ 源清单里落盘缺失的个数
  local root f
  while read -r f; do
    for root in $1; do [ -f "$root/${f:0:2}/${f:2}" ] && continue 2; done
    echo x
  done < "$SFLIST" | wc -l
}
m19=$(cnt_missing "$FS19"); m20=$(cnt_missing "$FS20")
printf '%-20s %-17s %-17s %s\n' "attach_src_files" "$(wc -l < "$SFLIST")" "$(wc -l < "$SFLIST")" OK
j=OK
if [ "$m19" != 0 ]; then j="FAIL(源侧自身缺 $m19)"; BADD=$((BADD+1))
elif [ "$m20" != 0 ]; then j="FAIL(目标侧缺 $m20)"; BADD=$((BADD+1)); fi
printf '%-20s %-17s %-17s %s\n' "attach_files_missing" "$m19" "$m20" "$j"

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
# 权限组：res_groups 是 DENY 端（20 自建、两侧同组不同 id）→ 只能按 XMLID 映射，
# 因此成员关系**允许少于源侧**（20 侧确实没有那个组时）。但它必须是"映射后"而不是
# "没映射"：admin 一组都没有 = 所有 tour.* 都 AccessError，业务侧看到的就是空界面。
G19=$(run "$SRC_C" "$SRC_DB" "select count(*) from res_groups_users_rel")
G20=$(run "$DST_C" "$DST_DB" "select count(*) from res_groups_users_rel")
U20=$(run "$DST_C" "$DST_DB" "select count(distinct uid) from res_groups_users_rel")
A20=$(run "$DST_C" "$DST_DB" "select count(*) from res_groups_users_rel r join res_users u on u.id=r.uid where u.login='admin'")
j=OK
if [ "${A20:-0}" = 0 ]; then j="FAIL(admin 零组 → 组映射未跑)"; BADD=$((BADD+1)); fi
printf '%-20s %-17s %-17s %s\n' "group_members" "$G19" "$G20" "$j（覆盖用户 $U20 个，admin $A20 组）"

printf '%s\n' "------------------------------------------------------------------------------"
echo "差异判据数: $BADD"
[ "$BADD" = 0 ] || exit 1
