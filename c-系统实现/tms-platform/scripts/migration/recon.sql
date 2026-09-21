-- TMS/TOUR 数据库一致性指纹（迁移对账用）
-- 用法：bash scripts/migration/recon.sh <pg容器> <库名> > out.tsv
-- 输出为 key<TAB>value 的 TSV，两次运行结果可直接 diff（A0 恢复演练、A1 平桥核对、B2 ETL 对账共用）
-- 说明：列名按 Odoo 19 现网校验（account_move_line 无 reconcile_id；partial 走 debit_move_id/credit_move_id
--       成对行，无 amount_type；ir_attachment 用 checksum 而非 digest）。Odoo 20 侧若列有增删，recon 会直接报错，
--       这正是"结构漂移"的探针，按 B0 的字段 diff 报告调整即可。
\pset footer off
\pset tuples_only on
\pset fieldsep '	'

-- ============ 1. 逐表精确行数（全部用户表，含空表） ============
-- 不能用 pg_stat_user_tables.n_live_tup>0 来筛表：那是 ANALYZE/VACUUM 维护的估算值，
-- 生产库常年只读的小表 n_live_tup 会是 0，而刚 ANALYZE 过的恢复库却有值，
-- 两侧表集合直接对不上（A0 首次演练实测：108/198 条差异全由此产生）。
CREATE TEMP TABLE recon_counts (key text PRIMARY KEY, value text);

SELECT string_agg(
         format('INSERT INTO recon_counts SELECT %L, count(*)::text FROM %I.%I ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value',
                n.nspname || '.' || c.relname, n.nspname, c.relname),
         E';\n')
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind IN ('r', 'p')
   AND n.nspname NOT LIKE 'pg\_%'
   AND n.nspname <> 'information_schema'
\gexec

-- ============ 2. 金额与结构不变量 ============
INSERT INTO recon_counts
SELECT key, value FROM (
  SELECT 'sum|aml.debit' AS key, to_char(coalesce(sum(debit),0),'FM999999999999990.00') AS value FROM account_move_line
  UNION ALL
  SELECT 'sum|aml.credit', to_char(coalesce(sum(credit),0),'FM999999999999990.00') FROM account_move_line
  UNION ALL
  SELECT 'sum|aml.balance', to_char(coalesce(sum(balance),0),'FM999999999999990.00') FROM account_move_line
  -- 凭证级平衡：已过账单据的分录 balance 合计必须为 0
  -- （单账户借贷不等是正常的，因此不能按 account_id 判定）
  UNION ALL
  SELECT 'count|move.unbalanced_posted', count(*)::text FROM (
      SELECT l.move_id FROM account_move_line l JOIN account_move m ON m.id = l.move_id
       WHERE m.state = 'posted' GROUP BY l.move_id HAVING abs(sum(l.balance)) > 0.005) u
  UNION ALL
  SELECT 'sum|move.amount_total', to_char(coalesce(sum(amount_total),0),'FM999999999999990.00') FROM account_move
  UNION ALL
  SELECT 'sum|move.amount_residual', to_char(coalesce(sum(amount_residual),0),'FM999999999999990.00') FROM account_move
  -- 核销不变量：matching_number 必须等于 str(full_reconcile_id.id)（Odoo 20 同约束）
  UNION ALL
  SELECT 'count|aml.matching_violation', count(*)::text FROM account_move_line
    WHERE full_reconcile_id IS NOT NULL
      AND nullif(matching_number,'') IS DISTINCT FROM full_reconcile_id::text
  -- 核销标记与 full_reconcile 一致性（残差/关联完整性探针）
  UNION ALL
  SELECT 'count|aml.reconciled_no_full', count(*)::text FROM account_move_line
    WHERE reconciled AND full_reconcile_id IS NULL
  -- 成对核销完整性：每条 partial 的借贷两侧行必须存在
  UNION ALL
  SELECT 'count|partial.dangling', count(*)::text FROM account_partial_reconcile p
    WHERE NOT EXISTS (SELECT 1 FROM account_move_line l WHERE l.id = p.debit_move_id)
       OR NOT EXISTS (SELECT 1 FROM account_move_line l WHERE l.id = p.credit_move_id)
) c
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- ============ 3. 关键表行内容指纹（md5，捕获"行数相同但内容不同"） ============
INSERT INTO recon_counts
SELECT key, value FROM (
  SELECT 'md5|account_move' AS key,
         md5(string_agg(id::text || '|' || coalesce(name,'') || '|' || coalesce(state,'') || '|'
                        || to_char(coalesce(amount_total,0),'FM99999990.00') || '|'
                        || coalesce(to_char(date,'YYYY-MM-DD'),''), ',' ORDER BY id)) AS value
    FROM account_move
  UNION ALL
  SELECT 'md5|account_move_line',
         md5(string_agg(id::text || '|' || coalesce(move_id::text,'') || '|' || coalesce(account_id::text,'') || '|'
                        || to_char(coalesce(debit,0),'FM99999990.00') || '|'
                        || to_char(coalesce(credit,0),'FM99999990.00') || '|'
                        || to_char(coalesce(balance,0),'FM99999990.00') || '|'
                        || coalesce(full_reconcile_id::text,'') || '|'
                        || coalesce(matching_number,'') || '|'
                        || coalesce(reconciled::text,''), ',' ORDER BY id))
    FROM account_move_line
  UNION ALL
  SELECT 'md5|account_partial_reconcile',
         md5(string_agg(id::text || '|' || to_char(coalesce(amount,0),'FM99999990.00') || '|'
                        || coalesce(debit_move_id::text,'') || '-' || coalesce(credit_move_id::text,'') || '|'
                        || coalesce(to_char(max_date,'YYYY-MM-DD'),''), ',' ORDER BY id))
    FROM account_partial_reconcile
  UNION ALL
  -- 注意：Odoo 19 起「可翻译字段」落盘为 jsonb（res_partner.name 即如此），
  -- 指纹里必须 ::text 后再拼接；这对 B2 ETL 也是同一类坑（翻译字段不能按 varchar 直搬）。
  SELECT 'md5|res_partner',
         md5(string_agg(id::text || '|' || coalesce(name::text,'') || '|' || coalesce(email,'') || '|'
                        || coalesce(phone,''), ',' ORDER BY id))
    FROM res_partner
  UNION ALL
  SELECT 'md5|res_users',
         md5(string_agg(id::text || '|' || coalesce(login,'') || '|' || coalesce(left(password,12),'') || '|'
                        || coalesce(active::text,''), ',' ORDER BY id))
    FROM res_users
  UNION ALL
  SELECT 'md5|ir_attachment',
         md5(string_agg(id::text || '|' || coalesce(res_model,'') || '-' || coalesce(res_id::text,'') || '|'
                        || coalesce(store_fname,'') || '|' || coalesce(file_size::text,'') || '|'
                        || coalesce(checksum,''), ',' ORDER BY id))
    FROM ir_attachment
  UNION ALL
  SELECT 'md5|ir_model_data',
         md5(string_agg(coalesce(module,'') || '.' || coalesce(name,'') || '=' || coalesce(res_id::text,''), ',' ORDER BY id))
    FROM ir_model_data
  UNION ALL
  SELECT 'md5|ir_sequence',
         md5(string_agg(id::text || '|' || coalesce(prefix,'') || '|' || coalesce(number_next::text,'') || '|'
                        || coalesce(number_increment::text,''), ',' ORDER BY id))
    FROM ir_sequence
  UNION ALL
  SELECT 'md5|tour_key_tables',
         md5(string_agg(t.tbl || ':' || t.cnt::text, ',' ORDER BY t.tbl))
    FROM (SELECT 'tour_guide' tbl, count(*) cnt FROM tour_guide
          UNION ALL SELECT 'tour_payment_claim', count(*) FROM tour_payment_claim
          UNION ALL SELECT 'tour_plan_reg', count(*) FROM tour_plan_reg
          UNION ALL SELECT 'tour_plan_reg_passenger', count(*) FROM tour_plan_reg_passenger) t
  -- 敏感字段加密落盘口径（密文/明文比例必须搬迁前后一致，防明文污染）
  UNION ALL
  SELECT 'md5|encrypted_fields',
         md5(string_agg(k || ':' || v::text, ',' ORDER BY k))
    FROM (SELECT 'plan_reg.cipher' k, count(*) v FROM tour_plan_reg WHERE supplier_user_mobile ~ '^AQ'
          UNION ALL SELECT 'plan_reg.plain', count(*) FROM tour_plan_reg
            WHERE nullif(supplier_user_mobile,'') IS NOT NULL AND supplier_user_mobile !~ '^AQ'
          UNION ALL SELECT 'plan_reg.hash', count(*) FROM tour_plan_reg
            WHERE nullif(supplier_user_mobile_hash,'') IS NOT NULL
          UNION ALL SELECT 'pax.id_number_cipher', count(*) FROM tour_plan_reg_passenger WHERE id_number ~ '^AQ'
          UNION ALL SELECT 'pax.id_number_plain', count(*) FROM tour_plan_reg_passenger
            WHERE nullif(id_number,'') IS NOT NULL AND id_number !~ '^AQ') e
) c
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

SELECT key, value FROM recon_counts ORDER BY key;
