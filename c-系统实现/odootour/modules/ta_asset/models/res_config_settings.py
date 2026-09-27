# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ta_asset_depreciation_account_id = fields.Many2one(
        'account.account', string='折旧费用科目',
        config_parameter='ta_asset.depreciation_account_id')
    ta_asset_accumulated_account_id = fields.Many2one(
        'account.account', string='累计折旧科目',
        config_parameter='ta_asset.accumulated_account_id')
