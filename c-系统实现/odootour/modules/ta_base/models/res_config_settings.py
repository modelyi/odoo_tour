# -*- coding: utf-8 -*-
from odoo import models, fields


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
