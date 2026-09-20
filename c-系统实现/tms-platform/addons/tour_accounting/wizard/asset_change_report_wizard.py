# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AssetChangeReportWizard(models.TransientModel):
    _name = 'asset.change.report.wizard'
    _description = 'Asset Change Report Wizard'

    date_from = fields.Date(string='开始日期', required=True,
                            default=fields.Date.today().replace(month=1, day=1))
    date_to = fields.Date(string='结束日期', required=True,
                          default=fields.Date.today())
    category_id = fields.Many2one('account.asset.category', string='资产类别')
    company_id = fields.Many2one('res.company', string='公司',
                                 default=lambda self: self.env.company)

    def action_print_report(self):
        self.ensure_one()
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'category_id': self.category_id.id if self.category_id else False,
            'company_id': self.company_id.id,
        }
        return self.env.ref('tour_accounting.action_report_asset_change').report_action(self, data=data)
