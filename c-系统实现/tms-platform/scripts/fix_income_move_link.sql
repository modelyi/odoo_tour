-- P0-2 修复：回填收入确认凭证回链（income_move_id）
-- 背景：收入确认的幂等只认 tour_plan.income_move_id，但批量过账脚本生成的收入凭证
--       未回写该字段（33,926 个团账上已有 6001.0x 收入行却无回链），再跑一次会重复确认收入。
-- 关联方式：收入凭证 account.move（entry）的 6001.0x 行带 analytic_distribution → 团分析账户 → tour_plan。
-- 幂等：只填 income_move_id IS NULL 的；先备份。
-- 执行：docker exec -i tms-db psql -U odoo -d tms < fix_income_move_link.sql

BEGIN;

DROP TABLE IF EXISTS bak_tour_plan_income_move;
CREATE TABLE bak_tour_plan_income_move AS
  SELECT id, income_move_id FROM tour_plan;

WITH rev AS (
  SELECT l.move_id, (k.key)::int AS analytic_id
  FROM account_move_line l
  JOIN account_move m ON m.id = l.move_id
  JOIN account_account a ON a.id = l.account_id
  CROSS JOIN LATERAL jsonb_object_keys(l.analytic_distribution) AS k(key)
  WHERE a.code_store::text LIKE '%6001.0%'
    AND m.state = 'posted'
    AND m.move_type = 'entry'
    AND l.analytic_distribution IS NOT NULL
), pick AS (
  SELECT DISTINCT ON (analytic_id) analytic_id, move_id
  FROM rev
  ORDER BY analytic_id, move_id
)
UPDATE tour_plan p
SET income_move_id = pick.move_id
FROM account_analytic_account aa
JOIN pick ON pick.analytic_id = aa.id
WHERE aa.tour_plan_id = p.id
  AND p.income_move_id IS NULL;

COMMIT;
