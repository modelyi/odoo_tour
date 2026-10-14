# -*- coding: utf-8 -*-
from odoo import models, fields


class TaGuidePerformance(models.Model):
    """导游绩效表（迭代4）：粒度 = 导游 × 带团月。
    团数/收入/成本按发团计划 guide_ids（res.users→partner）归集；
    报账/佣金按导游 partner + 月份归集；借支未清为当前余额（同导游各月同值）。
    毛利口径同 BS-19：收入-（已确认计调单 + 已审核导游报账）。SQL 视图，只读。
    """
    _name = 'ta.guide.performance'
    _description = '导游绩效'
    _auto = False
    _order = 'ym desc, tour_count desc'

    guide_id = fields.Many2one('res.partner', string='导游', readonly=True)
    ym = fields.Char(string='带团月', readonly=True)
    tour_count = fields.Integer(string='带团数', readonly=True)
    heads = fields.Integer(string='服务人数', readonly=True)
    income = fields.Float(string='团收入（已确认订单）', readonly=True)
    cost_total = fields.Float(string='团成本（计调+报账）', readonly=True)
    profit = fields.Float(string='团毛利（BS-19）', readonly=True)
    expense_count = fields.Integer(string='报账单数', readonly=True)
    expense_lag_days = fields.Float(string='平均报账时效（天）', readonly=True)
    commission_net = fields.Float(string='佣金净额（税后）', readonly=True)
    loan_outstanding = fields.Float(string='借支未结清（当前）', readonly=True)
    company_id = fields.Many2one('res.company', string='公司', readonly=True)

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_guide_performance AS
            WITH dep_agg AS (  -- 每个发团计划的团级指标（同 BS-19 口径）
                SELECT d.id AS departure_id,
                       to_char(d.date_start, 'YYYY-MM') AS ym,
                       d.company_id,
                       COALESCE((SELECT sum(o.heads) FROM ta_order o
                                  WHERE o.departure_id = d.id
                                    AND o.state IN ('confirmed','tripping','settled')), 0) AS heads,
                       COALESCE((SELECT sum(o.amount_paid) FROM ta_order o
                                  WHERE o.departure_id = d.id
                                    AND o.state IN ('confirmed','tripping','settled')), 0) AS income,
                       COALESCE((SELECT sum(i.amount) FROM ta_dispatch_item i
                                  WHERE i.departure_id = d.id AND i.state = 'confirmed'), 0)
                       + COALESCE((SELECT sum(g.amount_total) FROM ta_guide_expense g
                                    WHERE g.departure_id = d.id AND g.state = 'approved'), 0)
                       AS cost
            FROM ta_departure d
            WHERE d.date_start IS NOT NULL
            ),
            tours AS (  -- 导游 × 团（经 res.users 展开 guide_ids）
                SELECT p.id AS guide_id, da.*
                FROM dep_agg da
                JOIN res_users_ta_departure_rel rel ON rel.ta_departure_id = da.departure_id
                JOIN res_users uu ON uu.id = rel.res_users_id
                JOIN res_partner p ON p.id = uu.partner_id
            )
            SELECT (t.guide_id::text || '_' || t.ym) AS id,
                   t.guide_id AS guide_id,
                   t.ym AS ym,
                   count(DISTINCT t.departure_id)::int AS tour_count,
                   sum(t.heads)::int AS heads,
                   sum(t.income) AS income,
                   sum(t.cost) AS cost_total,
                   sum(t.income) - sum(t.cost) AS profit,
                   COALESCE(ex.expense_count, 0)::int AS expense_count,
                   ex.avg_lag AS expense_lag_days,
                   COALESCE(cm.commission_net, 0) AS commission_net,
                   COALESCE(ln.loan_outstanding, 0) AS loan_outstanding,
                   max(t.company_id) AS company_id
            FROM tours t
            LEFT JOIN (
                -- 报账单数按带团月归属（发团日所在月），与成本口径一致（批6 P1-6）
                SELECT g.guide_id, to_char(d.date_start, 'YYYY-MM') AS ym,
                       count(*) AS expense_count,
                       avg(g.date - d.date_end)::float AS avg_lag
                FROM ta_guide_expense g
                JOIN ta_departure d ON d.id = g.departure_id
                WHERE g.state IN ('submitted','approved')
                GROUP BY g.guide_id, to_char(d.date_start, 'YYYY-MM')
            ) ex ON ex.guide_id = t.guide_id AND ex.ym = t.ym
            LEFT JOIN (
                SELECT c.guide_id, to_char(d.date_start, 'YYYY-MM') AS ym,
                       sum(c.net_amount) AS commission_net
                FROM ta_guide_commission c
                JOIN ta_departure d ON d.id = c.departure_id
                WHERE c.state = 'settled'
                GROUP BY c.guide_id, to_char(d.date_start, 'YYYY-MM')
            ) cm ON cm.guide_id = t.guide_id AND cm.ym = t.ym
            LEFT JOIN (
                SELECT l.guide_id, sum(l.outstanding) AS loan_outstanding
                FROM ta_guide_loan l
                WHERE l.state IN ('approved','paid')
                GROUP BY l.guide_id
            ) ln ON ln.guide_id = t.guide_id
            GROUP BY t.guide_id, t.ym, ex.expense_count, ex.avg_lag,
                     cm.commission_net, ln.loan_outstanding
        """)
