# -*- coding: utf-8 -*-
from odoo import models, fields


class TaReceivableAging(models.Model):
    """应收账龄（迭代3）：order 维度未收余额 × 逾期桶。

    锚点 = 最早未清期次 due_date（amount_paid < amount），无期次/全清回退
    订单确认日 date_confirm，再回退发团计划出发日。只按有效订单
    （confirmed/tripping/settled）统计，settled 理论零余额但保留防口径漏。
    """
    _name = 'ta.receivable.aging'
    _description = '应收账龄'
    _auto = False
    _order = 'date_oldest asc'

    order_id = fields.Many2one('ta.order', string='订单', readonly=True)
    order_name = fields.Char(string='订单号', readonly=True)
    partner_id = fields.Many2one('res.partner', string='客户', readonly=True)
    departure_id = fields.Many2one('ta.departure', string='发团计划', readonly=True)
    route_name = fields.Char(string='线路', readonly=True)
    state = fields.Selection([
        ('draft', '草稿'), ('confirmed', '已确认'), ('tripping', '行程中'),
        ('settled', '已结算'), ('cancel', '已取消'),
    ], string='订单状态', readonly=True)
    date_oldest = fields.Date(string='账龄锚点', readonly=True)
    amount_total = fields.Float(string='应收总额', readonly=True)
    amount_paid = fields.Float(string='已收', readonly=True)
    amount_open = fields.Float(string='未收余额', readonly=True)
    bucket = fields.Selection([
        ('b0_30', '未逾期~30天'),
        ('b31_60', '31-60天'),
        ('b61_90', '61-90天'),
        ('b90p', '90天以上'),
    ], string='账龄桶', readonly=True)
    days_overdue = fields.Integer(string='逾期天数', readonly=True)
    company_id = fields.Many2one('res.company', string='公司', readonly=True)

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_receivable_aging AS
            WITH anchor AS (
                SELECT o.id AS order_id,
                       COALESCE(
                           (SELECT min(p.due_date) FROM ta_receivable_plan p
                             WHERE p.order_id = o.id
                               AND COALESCE(p.amount_paid, 0) < p.amount - 0.01),
                           o.date_confirm,
                           d.date_start) AS date_oldest
                FROM ta_order o
                JOIN ta_departure d ON d.id = o.departure_id
                WHERE o.state IN ('confirmed', 'tripping', 'settled')
                  AND o.amount_open > 0.01
            )
            SELECT o.id AS id,
                   o.id AS order_id,
                   o.name AS order_name,
                   o.partner_id AS partner_id,
                   o.departure_id AS departure_id,
                   r.name AS route_name,
                   o.state::text AS state,
                   a.date_oldest AS date_oldest,
                   o.amount_total AS amount_total,
                   o.amount_paid AS amount_paid,
                   o.amount_open AS amount_open,
                   GREATEST(0, (CURRENT_DATE - a.date_oldest))::int AS days_overdue,
                   CASE
                     WHEN (CURRENT_DATE - a.date_oldest) <= 30 THEN 'b0_30'
                     WHEN (CURRENT_DATE - a.date_oldest) <= 60 THEN 'b31_60'
                     WHEN (CURRENT_DATE - a.date_oldest) <= 90 THEN 'b61_90'
                     ELSE 'b90p' END::text AS bucket,
                   o.company_id AS company_id
            FROM ta_order o
            JOIN anchor a ON a.order_id = o.id
            JOIN ta_departure d ON d.id = o.departure_id
            JOIN ta_route r ON r.id = d.route_id
        """)
