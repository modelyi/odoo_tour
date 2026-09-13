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
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """Inherits from the account.move model for adding the depreciation
    field to the account"""
    _inherit = 'account.move'

    has_due = fields.Boolean(string='Has due')
    is_warning = fields.Boolean(string='Is warning')
    due_amount = fields.Float(string="Due Amount",
                              related='partner_id.due_amount')
    recurring_ref = fields.Char(string='Recurring Ref')
    recurring_invoice_id = fields.Many2one(
        'account.recurring.invoice', string='Recurring Invoice',
        copy=False, index='btree_not_null',
        help="The recurring template that generated this invoice.")
    asset_depreciation_ids = fields.One2many('account.asset.depreciation.line',
                                             'move_id',
                                             string='Assets Depreciation Lines')
    to_check = fields.Boolean(string='To Check', tracking=True,
                              help="If this checkbox is ticked, it means that the user was not sure of all the related "
                                   "information at the time of the creation of the move and that the move needs to be "
                                   "checked again.",
                              )

    def button_cancel(self):
        """Button action to cancel the transfer"""
        for move in self:
            for line in move.asset_depreciation_ids:
                line.move_posted_check = False
        return super().button_cancel()

    def action_cancel(self):
        """Action perform to cancel the asset record"""
        res = super().action_cancel()
        self.env['account.asset.asset'].sudo().search(
            [('invoice_id', 'in', self.ids)]).write({'active': False})
        return res

    def action_post(self):
        """To check the selected customers due amount is exceed than blocking stage"""
        pay_type = ['out_invoice', 'out_refund', 'out_receipt']
        for rec in self:
            if rec.partner_id.active_limit and rec.move_type in pay_type \
                    and rec.partner_id.enable_credit_limit:
                if rec.due_amount >= rec.partner_id.blocking_stage and rec.partner_id.blocking_stage != 0:
                    raise UserError(_(
                        "%s is in  Blocking Stage and "
                        "has a due amount of %s %s to pay") % (
                                        rec.partner_id.name, rec.due_amount,
                                        rec.currency_id.symbol))

        result = super().action_post()
        # Post the linked asset depreciation lines and close fully
        # depreciated assets (previously handled by the dead ``post`` override).
        self.mapped('asset_depreciation_ids').post_lines_and_close_asset()
        for inv in self:
            context = dict(self.env.context)
            # Within the context of an invoice,
            # this default value is for the type of the invoice, not the type
            # of the asset. This has to be cleaned from the context before
            # creating the asset,otherwise it tries to create the asset with
            # the type of the invoice.
            context.pop('default_type', None)
            inv.invoice_line_ids.with_context(context).asset_create()
        return result

    @api.onchange('partner_id')
    def check_due(self):
        """To show the due amount and warning stage"""
        if self.partner_id and self.partner_id.due_amount > 0 \
                and self.partner_id.active_limit \
                and self.partner_id.enable_credit_limit:
            self.has_due = True
        else:
            self.has_due = False
        if self.partner_id and self.partner_id.active_limit \
                and self.partner_id.enable_credit_limit:
            if self.due_amount >= self.partner_id.warning_stage:
                if self.partner_id.warning_stage != 0:
                    self.is_warning = True
        else:
            self.is_warning = False


# === 合规标注：每条凭证必须标注适用的准则/法规依据 [BS-10 §9.1 / D7]（合并自 tour_finance）===
COMPLIANCE_REF_SELECTION = [
    ('cas14', '[CAS 14] 收入'),
    ('cas14_agent', '[CAS 14-代理人] 净额法'),
    ('cas14_principal', '[CAS 14-主要责任人] 总额法'),
    ('cas14_advance', '[CAS 14-预收]'),
    ('cas22', '[CAS 22] 金融工具确认和计量'),
    ('cas22_settle', '[CAS 22-核销]'),
    ('cas1', '[CAS 1] 存货/成本归集'),
    ('cas8', '[CAS 8] 资产减值'),
    ('cas9', '[CAS 9] 职工薪酬'),
    ('cas30', '[CAS 30] 财务报表列报'),
    ('cas37', '[CAS 37] 金融工具列报'),
    ('vat_diff', '[财税2016-36号] 差额征税'),
    ('vat_reg', '[增值税暂行条例]'),
    ('iit', '[个税法] 代扣代缴'),
    ('iit_labor', '[个税法-劳务报酬]'),
    ('stamp', '[印花税法]'),
    ('ic_sep', '[内控-职务分离]'),
    ('ic_auth', '[内控-授权审批]'),
    ('ic_refund', '[内控-退款审批]'),
    ('ic_audit', '[内控-审计轨迹]'),
    ('pay_settle', '[支付结算办法]'),
    ('cash_reg', '[现金管理暂行条例]'),
]


class AccountMoveCompliance(models.Model):
    _inherit = 'account.move'

    compliance_ref = fields.Selection(
        COMPLIANCE_REF_SELECTION, string='准则依据',
        help='每条凭证必须标注适用的准则/法规依据 [BS-10 §9.1]')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    compliance_ref = fields.Selection(
        COMPLIANCE_REF_SELECTION, string='准则依据(行级)',
        help='凭证跨多准则时按行覆盖主凭证标签；默认继承 account.move.compliance_ref')
