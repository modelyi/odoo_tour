# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # 单团核算毛利口径开关（BS-19）：勾选=成本按含税录入并自动做
    # cost_net = cost_total/(1+r) 拆分；两口径互斥防双重扣减。ta_finance 落地口径计算。
    ta_cost_tax_split = fields.Boolean(
        string='成本含税拆分（差额征税口径）',
        config_parameter='ta_base.cost_tax_split', default=False)
    ta_default_tax_rate = fields.Float(
        string='成本默认税率 r（小数，如 0.06）',
        config_parameter='ta_base.default_tax_rate', default=0.0)

    # 批6 P0-6：收入成本确认公司级配置（直连 res.company，不同公司可不同做法）
    ta_taxpayer_type = fields.Selection(
        related='company_id.ta_taxpayer_type', readonly=False,
        string='纳税人身份')
    ta_vat_rate = fields.Float(
        related='company_id.ta_vat_rate', readonly=False,
        string='收入增值税率（小数）')
    ta_revenue_dd_split_tax = fields.Boolean(
        related='company_id.ta_revenue_dd_split_tax', readonly=False,
        string='41 代订差价拆销项税')
    ta_revenue_auto_on_depart = fields.Boolean(
        related='company_id.ta_revenue_auto_on_depart', readonly=False,
        string='发团自动确认收入')

    @api.onchange('ta_taxpayer_type')
    def _onchange_ta_taxpayer_type(self):
        if self.ta_taxpayer_type:
            self.ta_vat_rate = (
                0.06 if self.ta_taxpayer_type == 'general' else 0.03)
