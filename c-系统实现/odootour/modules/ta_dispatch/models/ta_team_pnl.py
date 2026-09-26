# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TaTeamPnl(models.Model):
    """单团核算（BS-19 口径）：收入=已审核认领到本团订单的金额；
    成本=已确认派工条目 +（M4 追加）导游报账。SQL 视图聚合，只读。
    """
    _name = 'ta.team.pnl'
    _description = '单团损益'
    _auto = False
    _order = 'date_start desc'

    departure_id = fields.Many2one('ta.departure', string='班期', readonly=True)
    route_name = fields.Char(string='线路', readonly=True)
    code = fields.Char(string='班期号', readonly=True)
    date_start = fields.Date(string='出发日', readonly=True)
    company_id = fields.Many2one('res.company', string='公司', readonly=True)
    state = fields.Selection(related='departure_id.state', string='班期状态')
    seats_used = fields.Integer(string='报名人数', readonly=True)
    income = fields.Float(string='已收款', readonly=True)
    order_total = fields.Float(string='订单总额', readonly=True)
    cost_total = fields.Float(string='成本（含税）', readonly=True)

    @api.depends('income', 'cost_total')
    @api.depends_context('company')
    def _compute_tax_split(self):
        icp = self.env['ir.config_parameter'].sudo()
        split = icp.get_bool('ta_base.cost_tax_split', False)
        rate = icp.get_float('ta_base.default_tax_rate', 0.0)
        for pnl in self:
            cost_net = pnl.cost_total / (1.0 + rate) if (split and rate) else pnl.cost_total
            pnl.cost_net = cost_net
            pnl.profit = pnl.income - cost_net
            pnl.profit_tax_incl = pnl.income - pnl.cost_total

    cost_net = fields.Float(string='成本（不含税净额）', compute='_compute_tax_split')
    profit = fields.Float(string='单团毛利（BS-19）', compute='_compute_tax_split')
    profit_tax_incl = fields.Float(string='毛利（含税口径）', compute='_compute_tax_split')

    def init(self):
        # 收入口径：订单 amount_paid 仅在认领审核后写入（ta_finance），天然=已审核收款。
        # NFR-1：全部直取原值，不做 abs() 方向修正。
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ta_team_pnl AS
            SELECT d.id AS id,
                   d.id AS departure_id,
                   r.name AS route_name,
                   d.code AS code,
                   d.date_start AS date_start,
                   d.company_id AS company_id,
                   d.seats_used AS seats_used,
                   COALESCE((SELECT sum(o.amount_paid) FROM ta_order o
                              WHERE o.departure_id = d.id
                                AND o.state IN ('confirmed','tripping','settled')), 0) AS income,
                   COALESCE((SELECT sum(o.amount_total) FROM ta_order o
                              WHERE o.departure_id = d.id
                                AND o.state IN ('confirmed','tripping','settled')), 0) AS order_total,
                   COALESCE((SELECT sum(i.amount) FROM ta_dispatch_item i
                              WHERE i.departure_id = d.id AND i.state = 'confirmed'), 0) AS cost_total
            FROM ta_departure d
            JOIN ta_route r ON r.id = d.route_id
        """)
