# -*- coding: utf-8 -*-
from odoo import models, fields


class TaScenicContribution(models.Model):
    """景点毛利贡献（迭代5）：粒度 = 景点供应商 × 发团计划。
    景点维度 = 计调单 kind∈(ticket,scenic) 的供应商；
    毛利贡献 = 团毛利（BS-19 含税口径）× 该景点门票成本 ÷ 全团成本（成本 0 不除零）。
    SQL 视图聚合，只读。
    """
    _name = 'ta.scenic.contribution'
    _description = '景点毛利贡献'
    _auto = False
    _order = 'date_start desc, profit_contribution desc'

    departure_id = fields.Many2one('ta.departure', string='发团计划', readonly=True)
    supplier_id = fields.Many2one('res.partner', string='景点供应商', readonly=True)
    code = fields.Char(string='计划号', readonly=True)
    route_name = fields.Char(string='线路', readonly=True)
    date_start = fields.Date(string='出发日', readonly=True)
    ticket_cost = fields.Float(string='门票成本', readonly=True)
    cost_total = fields.Float(string='全团成本', readonly=True)
    income = fields.Float(string='团收入', readonly=True)
    profit = fields.Float(string='团毛利（含税口径）', readonly=True)
    cost_ratio = fields.Float(string='门票成本占比', readonly=True)
    profit_contribution = fields.Float(string='毛利贡献', readonly=True)
    company_id = fields.Many2one('res.company', string='公司', readonly=True)

    def init(self):
        # ta_guide_expense 属 ta_guide（本模块不依赖）：存在才并入成本，口径同 ta.team.pnl
        self.env.cr.execute("SELECT to_regclass('ta_guide_expense')")
        has_expense = bool(self.env.cr.fetchone()[0])
        expense_sql = ("COALESCE((SELECT sum(g.amount_total) FROM ta_guide_expense g"
                       " WHERE g.departure_id = d.id AND g.state = 'approved'), 0)"
                       if has_expense else "0")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_scenic_contribution AS
            WITH scenic AS (  -- 景点供应商 × 团 的门票成本
                SELECT i.departure_id, i.supplier_id, sum(i.amount) AS ticket_cost
                FROM ta_dispatch_item i
                WHERE i.state = 'confirmed' AND i.kind IN ('ticket', 'scenic')
                GROUP BY i.departure_id, i.supplier_id
            ),
            dep AS (  -- 团级口径（同 ta.team.pnl BS-19）
                SELECT d.id AS departure_id,
                       COALESCE((SELECT sum(o.amount_paid) FROM ta_order o
                                  WHERE o.departure_id = d.id
                                    AND o.state IN ('confirmed','tripping','settled')), 0) AS income,
                       COALESCE((SELECT sum(i.amount) FROM ta_dispatch_item i
                                  WHERE i.departure_id = d.id AND i.state = 'confirmed'), 0)
                       + """ + expense_sql + """ AS cost_total
                FROM ta_departure d
            )
            SELECT (s.departure_id::text || '_' || s.supplier_id::text) AS id,
                   s.departure_id AS departure_id,
                   s.supplier_id AS supplier_id,
                   d.code AS code,
                   r.name AS route_name,
                   d.date_start AS date_start,
                   s.ticket_cost AS ticket_cost,
                   dp.cost_total AS cost_total,
                   dp.income AS income,
                   dp.income - dp.cost_total AS profit,
                   CASE WHEN dp.cost_total > 0.005
                        THEN round((s.ticket_cost / dp.cost_total * 100)::numeric, 2)
                        ELSE 0 END::float AS cost_ratio,
                   CASE WHEN dp.cost_total > 0.005
                        THEN round(((dp.income - dp.cost_total)
                                   * s.ticket_cost / dp.cost_total)::numeric, 2)
                        ELSE 0 END::float AS profit_contribution,
                   d.company_id AS company_id
            FROM scenic s
            JOIN ta_departure d ON d.id = s.departure_id
            JOIN ta_route r ON r.id = d.route_id
            JOIN dep dp ON dp.departure_id = s.departure_id
        """)
