# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # 用 related='company_id...' readonly=False 直接读写 res.company（真实落点），
    # 避免 ir.config_parameter 全局串扰——5 主体身份/税率可不同 [BS-11 §10.2]
    tour_taxpayer_type = fields.Selection(
        related='company_id.tour_taxpayer_type', readonly=False,
        string='纳税人身份')
    tour_vat_rate = fields.Float(
        related='company_id.tour_vat_rate', readonly=False,
        string='增值税税率(%)')
    tour_vat_levy_rate = fields.Float(
        related='company_id.tour_vat_levy_rate', readonly=False,
        string='征收率(%)')
    tour_diff_tax_enabled = fields.Boolean(
        related='company_id.tour_diff_tax_enabled', readonly=False,
        string='启用差额征税')
