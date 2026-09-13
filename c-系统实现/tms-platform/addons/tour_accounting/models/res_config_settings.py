# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    """Defines a model for configuration settings with additional fields for
     managing customer credit limit and Anglo-Saxon accounting settings."""
    _inherit = 'res.config.settings'

    customer_credit_limit = fields.Boolean(string="Customer Credit Limit")

    use_anglo_saxon_accounting = fields.Boolean(string="Use Anglo-Saxon accounting", readonly=False,
                                                related='company_id.anglo_saxon_accounting')
    fiscalyear_last_day = fields.Integer(
        related='company_id.fiscalyear_last_day', readonly=False
    )
    fiscalyear_last_month = fields.Selection(
        related='company_id.fiscalyear_last_month', readonly=False
    )
    fx_reval_journal_id = fields.Many2one(
        related='company_id.fx_reval_journal_id', readonly=False)
    fx_reval_gain_account_id = fields.Many2one(
        related='company_id.fx_reval_gain_account_id', readonly=False)
    fx_reval_loss_account_id = fields.Many2one(
        related='company_id.fx_reval_loss_account_id', readonly=False)

    @api.model
    def get_values(self):
        """Retrieve the values for configuration settings including the
         customer credit limit from the database parameters. """
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        customer_credit_limit = params.get_param('customer_credit_limit',
                                                 default=False)
        res.update(customer_credit_limit=customer_credit_limit)
        return res

    def set_values(self):
        """Set the customer credit limit value in the database parameters using superuser access."""
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            "customer_credit_limit",
            self.customer_credit_limit)

    @api.model
    def get_view_id(self):
        """Retrieve the ID of the view for bank reconciliation widget form."""
        view_id = self.env['ir.model.data']._xmlid_to_res_id(
            'tour_accounting.view_bank_reconcile_widget_form')
        return view_id


class ResConfigSettingsTourVat(models.TransientModel):
    """纳税人身份 / 税率 / 差额征税设置（合并自 tour_finance）[BS-11 §十]"""
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

    # === P2P 请款分级审批阈值（related 到 res.company，真实落点）[TDS §2.3] ===
    tour_pr_free_limit = fields.Float(
        related='company_id.tour_pr_free_limit', readonly=False,
        string='请款免审上限')
    tour_pr_approve_limit_l1 = fields.Float(
        related='company_id.tour_pr_approve_limit_l1', readonly=False,
        string='一级审批上限')
    tour_pr_approve_limit_l2 = fields.Float(
        related='company_id.tour_pr_approve_limit_l2', readonly=False,
        string='二级审批上限')
