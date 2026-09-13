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
from datetime import datetime
import calendar
from odoo import fields, models, api, _
from odoo.exceptions import RedirectWarning


class ResCompany(models.Model):
    """Model for inheriting res_company."""
    _inherit = "res.company"

    fx_reval_journal_id = fields.Many2one(
        'account.journal', string='FX Revaluation Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help="Journal used for foreign-currency revaluation entries.")
    fx_reval_gain_account_id = fields.Many2one(
        'account.account', string='Unrealized FX Gain Account',
        help="Account crediting the unrealized foreign-exchange gains.")
    fx_reval_loss_account_id = fields.Many2one(
        'account.account', string='Unrealized FX Loss Account',
        help="Account debiting the unrealized foreign-exchange losses.")

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure fiscal year day does not exceed the maximum valid day for the selected month during record creation."""
        for vals in vals_list:
            if 'fiscalyear_last_month' in vals and 'fiscalyear_last_day' in vals:
                month = vals.get('fiscalyear_last_month')
                day = vals.get('fiscalyear_last_day')
                if month and day:
                    opening_date = vals.get('account_opening_date')
                    if opening_date:
                        year = fields.Date.to_date(opening_date).year
                    else:
                        year = datetime.now().year
                    max_day = calendar.monthrange(year, int(month))[1]
                    if int(day) > max_day:
                        vals['fiscalyear_last_day'] = max_day
        return super().create(vals_list)

    def write(self, vals):
        """Auto-correct fiscal year day to a valid value when month or day is updated to prevent invalid calendar dates."""
        if 'fiscalyear_last_month' in vals or 'fiscalyear_last_day' in vals:
            month = vals.get('fiscalyear_last_month')
            day = vals.get('fiscalyear_last_day')
            if month:
                if self.account_opening_date:
                    year = self.account_opening_date.year
                else:
                    year = datetime.now().year
                max_day = calendar.monthrange(year, int(month))[1]
                if not day:
                    if any(company.fiscalyear_last_day > max_day for company in self):
                        vals['fiscalyear_last_day'] = max_day
                elif int(day) > max_day:
                    vals['fiscalyear_last_day'] = max_day

        return super().write(vals)

    def _validate_locks(self, values):
        """Validate the hard lock date by checking for unposted entries and unreconciled bank statement lines."""
        # Keep the standard lock-date validations provided by ``account``.
        super()._validate_locks(values)
        if values.get('hard_lock_date'):
            draft_entries = self.env['account.move'].search([
                ('company_id', 'in', self.ids),
                ('state', '=', 'draft'),
                ('date', '<=', values['hard_lock_date'])])
            if draft_entries:
                error_msg = _('There are still unposted entries in the '
                              'period you want to lock. You should either post '
                              'or delete them.')
                action_error = {
                    'view_mode': 'list',
                    'name': 'Unposted Entries',
                    'res_model': 'account.move',
                    'type': 'ir.actions.act_window',
                    'domain': [('id', 'in', draft_entries.ids)],
                    'search_view_id': [self.env.ref('account.view_account_move_filter').id, 'search'],
                    'views': [[self.env.ref('account.view_move_tree').id, 'list'], [self.env.ref('account.view_move_form').id, 'form']],
                }
                raise RedirectWarning(error_msg, action_error, _('Show unposted entries'))

            unreconciled_statement_lines = self.env['account.bank.statement.line'].search([
                ('company_id', 'in', self.ids),
                ('is_reconciled', '=', False),
                ('date', '<=', values['hard_lock_date']),
                ('move_id.state', 'in', ('draft', 'posted')),
            ])
            if unreconciled_statement_lines:
                error_msg = _("There are still unreconciled bank statement lines in the period you want to lock."
                            "You should either reconcile or delete them.")
                action_error = {
                    'view_mode': 'kanban',
                    'name': 'Unreconciled Transactions',
                    'res_model': 'account.bank.statement.line',
                    'type': 'ir.actions.act_window',
                    'domain': [('id', 'in', unreconciled_statement_lines.ids)],
                    'views': [[self.env.ref(
                        'tour_accounting.account_bank_statement_line_view_kanban').id,
                               'kanban']]
                }
                raise RedirectWarning(error_msg, action_error, _('Show Unreconciled Bank Statement Lines'))


class ResCompanyTourVat(models.Model):
    """纳税人身份 / 差额征税配置（合并自 tour_finance）[BS-11 §三]"""
    _inherit = 'res.company'

    tour_taxpayer_type = fields.Selection([
        ('general', '一般纳税人'),
        ('small', '小规模纳税人'),
    ], string='纳税人身份', default='general', required=True,
       help='决定增值税税率/征收率与计税分录口径 [BS-11 §三]')

    tour_vat_rate = fields.Float('增值税税率(%)', default=6.0, digits=(5, 2),
        help='一般纳税人税率，旅游服务默认 6% [财税2016-36号]')

    tour_vat_levy_rate = fields.Float('征收率(%)', default=3.0, digits=(5, 2),
        help='小规模征收率，默认 3%，优惠期减按 1% [财政部税务总局公告2023年第19号]')

    tour_diff_tax_enabled = fields.Boolean('启用差额征税', default=True,
        help='[财税2016-36号] 选择差额征税后 36 个月不得变更；'
             '关闭则走全额计税，不生成销项税额抵减分录')

    # === P2P 请款分级审批阈值 [TDS §2.3 / BS-06 §4.2] ===
    tour_pr_free_limit = fields.Float('请款免审上限', default=1000.0, digits=(16, 2),
        help='金额 ≤ 该值免审（默认 1000）')
    tour_pr_approve_limit_l1 = fields.Float('一级审批上限', default=50000.0, digits=(16, 2),
        help='金额 ≤ 该值走一级审批（默认 5 万）')
    tour_pr_approve_limit_l2 = fields.Float('二级审批上限', default=200000.0, digits=(16, 2),
        help='金额 ≤ 该值走二级审批（默认 20 万）；超过走三级双签')
