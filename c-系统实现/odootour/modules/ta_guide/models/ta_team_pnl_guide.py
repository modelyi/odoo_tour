# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TaTeamPnlGuide(models.Model):
    """单团核算扩展（BS-19）：已审核导游报账并入成本后重算净额与毛利。"""
    _inherit = 'ta.team.pnl'

    guide_expense_total = fields.Float(string='导游报账（审核后）', compute='_compute_guide_expense')

    @api.depends('departure_id')
    def _compute_guide_expense(self):
        expense_model = self.env['ta.guide.expense']
        for pnl in self:
            amounts = expense_model.search_read(
                [('departure_id', '=', pnl.departure_id.id), ('state', '=', 'approved')],
                ['amount_total'])
            pnl.guide_expense_total = sum(a['amount_total'] for a in amounts)

    @api.depends('income', 'cost_total', 'guide_expense_total')
    @api.depends_context('company')
    def _compute_tax_split(self):
        icp = self.env['ir.config_parameter'].sudo()
        split = icp.get_bool('ta_base.cost_tax_split', False)
        rate = icp.get_float('ta_base.default_tax_rate', 0.0)
        for pnl in self:
            cost_gross = pnl.cost_total + pnl.guide_expense_total
            cost_net = cost_gross / (1.0 + rate) if (split and rate) else cost_gross
            pnl.cost_net = cost_net
            pnl.profit = pnl.income - cost_net
            pnl.profit_tax_incl = pnl.income - cost_gross
