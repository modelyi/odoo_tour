# -*- coding: utf-8 -*-
from odoo import models, fields, api

from odoo.addons.ta_dispatch.models.ta_team_pnl import _ta_team_pnl_view_sql


class TaTeamPnlGuide(models.Model):
    """单团核算扩展（BS-19）：已审核导游报账并入成本后重算净额与毛利；
    批5-迭代3（P0-3 AC-16）：挂载购物佣金三列并重算含购物口径毛利。"""
    _inherit = 'ta.team.pnl'

    shop_commission = fields.Float(string='购物佣金（含税）', readonly=True, digits=(15, 2),
                                   help='= Σ 已确认/已结算购物佣金单的佣金总额（BS-08 经营收入）。')
    shop_commission_tax = fields.Float(string='购物佣金销项税', readonly=True, digits=(15, 2),
                                       help='= Σ 佣金增值税额（价税分离参考值，AC-19）。')
    shop_staff_cost = fields.Float(string='购物司陪分成', readonly=True, digits=(15, 2),
                                   help='= Σ 佣金单 allowance（各分成行税前应发合计）。')
    shop_cost = fields.Float(string='购物成本', readonly=True, digits=(15, 2),
                             help='= Σ 该团购物成本（回扣/礼品/其他，BS-08 §4.4，批6 P1-4）。')

    guide_expense_total = fields.Float(string='导游报账（审核后）', compute='_compute_guide_expense')

    def init(self):
        # ta_guide 更新时重建视图并挂购物佣金三列（SQL 由 ta_dispatch 统一组装，
        # 内部按 ta_guide_commission 表存在性自动挂列，两模块口径不漂移）。
        self.env.cr.execute(_ta_team_pnl_view_sql(self.env.cr))

    @api.depends('departure_id')
    def _compute_guide_expense(self):
        expense_model = self.env['ta.guide.expense']
        for pnl in self:
            amounts = expense_model.search_read(
                [('departure_id', '=', pnl.departure_id.id), ('state', '=', 'approved')],
                ['amount_total'])
            pnl.guide_expense_total = sum(a['amount_total'] for a in amounts)

    @api.depends('income', 'cost_total', 'guide_expense_total',
                 'shop_commission', 'shop_commission_tax', 'shop_staff_cost',
                 'shop_cost')
    @api.depends_context('company')
    def _compute_tax_split(self):
        icp = self.env['ir.config_parameter'].sudo()
        split = icp.get_bool('ta_base.cost_tax_split', False)
        rate = icp.get_float('ta_base.default_tax_rate', 0.0)
        for pnl in self:
            cost_gross = pnl.cost_total + pnl.guide_expense_total
            cost_net = cost_gross / (1.0 + rate) if (split and rate) else cost_gross
            pnl.cost_net = cost_net
            # AC-16 双口径：不含购物（BS-19 原口径）与含购物
            # （净佣金收入 − 司陪分成 − 购物成本，批6 P1-4）
            pnl.profit_no_shop = pnl.income - cost_net
            pnl.profit = (pnl.profit_no_shop
                          + (pnl.shop_commission - pnl.shop_commission_tax)
                          - pnl.shop_staff_cost - pnl.shop_cost)
            pnl.profit_tax_incl = pnl.income - cost_gross
