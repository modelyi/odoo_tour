-- 造销售渠道数据（tour_plan.channel_name / channel_id / from_type + tour_plan_reg.from_type 对齐）
-- 依据旅行社真实业务：直客门店/电话微信/企业客户/老客转介/同业分销/官网线上/电商平台(飞猪携程美团抖音)/内部员工团
-- 带年份趋势：2019-2021 门店+同业为主；2022-2023 电商上升；2024+ 线上为主
-- 幂等：先备份，可回滚；保留真实飞猪记录（channel_id=14563）
-- 执行：docker exec -i tms-db psql -U odoo -d tms < seed_sale_channel.sql

BEGIN;

DROP TABLE IF EXISTS bak_tour_plan_channel;
CREATE TABLE bak_tour_plan_channel AS
  SELECT id, from_type, channel_id, channel_name FROM tour_plan;

-- 保留 23 条真实飞猪，统一命名
UPDATE tour_plan SET channel_name='电商-飞猪', channel_id='401', from_type='7'
WHERE channel_id = '14563';

-- 其余按 年份档 x hash 桶 分配渠道
WITH base AS (
  SELECT id,
         EXTRACT(YEAR FROM COALESCE(begin_date, DATE '2023-06-01'))::int AS y,
         mod(abs(hashtext('salech_' || id::text)::bigint), 100) AS b
  FROM tour_plan
  WHERE COALESCE(channel_id, '') <> '14563'
     OR channel_id IS NULL
), m AS (
  SELECT id,
    CASE
      WHEN y <= 2021 THEN
        CASE WHEN b < 38 THEN '直客门店' WHEN b < 52 THEN '电话/微信直客'
             WHEN b < 58 THEN '企业客户' WHEN b < 63 THEN '老客转介'
             WHEN b < 91 THEN '同业分销' WHEN b < 94 THEN '官网线上'
             WHEN b < 97 THEN '电商-飞猪' WHEN b < 98 THEN '电商-携程'
             WHEN b < 99 THEN '电商-美团' ELSE '电商-抖音' END
      WHEN y <= 2023 THEN
        CASE WHEN b < 26 THEN '直客门店' WHEN b < 38 THEN '电话/微信直客'
             WHEN b < 44 THEN '企业客户' WHEN b < 49 THEN '老客转介'
             WHEN b < 71 THEN '同业分销' WHEN b < 79 THEN '官网线上'
             WHEN b < 87 THEN '电商-飞猪' WHEN b < 93 THEN '电商-携程'
             WHEN b < 97 THEN '电商-美团' WHEN b < 99 THEN '电商-抖音'
             ELSE '内部员工团' END
      ELSE
        CASE WHEN b < 18 THEN '直客门店' WHEN b < 28 THEN '电话/微信直客'
             WHEN b < 33 THEN '企业客户' WHEN b < 38 THEN '老客转介'
             WHEN b < 52 THEN '同业分销' WHEN b < 64 THEN '官网线上'
             WHEN b < 75 THEN '电商-飞猪' WHEN b < 84 THEN '电商-携程'
             WHEN b < 92 THEN '电商-美团' WHEN b < 99 THEN '电商-抖音'
             ELSE '内部员工团' END
    END AS ch
  FROM base
)
UPDATE tour_plan p SET
  channel_name = m.ch,
  channel_id = CASE m.ch
     WHEN '直客门店' THEN '101' WHEN '电话/微信直客' THEN '102'
     WHEN '企业客户' THEN '103' WHEN '老客转介' THEN '104'
     WHEN '内部员工团' THEN '105' WHEN '同业分销' THEN '201'
     WHEN '官网线上' THEN '301' WHEN '电商-飞猪' THEN '401'
     WHEN '电商-携程' THEN '402' WHEN '电商-美团' THEN '403'
     WHEN '电商-抖音' THEN '404' END,
  from_type = CASE m.ch
     WHEN '同业分销' THEN '5' WHEN '官网线上' THEN '6'
     WHEN '电商-飞猪' THEN '7' WHEN '电商-携程' THEN '7'
     WHEN '电商-美团' THEN '7' WHEN '电商-抖音' THEN '7'
     ELSE '1' END
FROM m WHERE p.id = m.id;

-- 报名单来源对齐其承载团
UPDATE tour_plan_reg r SET from_type = p.from_type
FROM tour_plan p
WHERE r.plan_id = p.id AND (r.from_type IS NULL OR r.from_type IS DISTINCT FROM p.from_type);

COMMIT;
