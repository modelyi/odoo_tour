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
from odoo import api, fields, models


# ---------------------------------------------------------
# Account Financial Report
# ---------------------------------------------------------
class AccountFinancialReport(models.Model):
    _name = "account.financial.report"
    _description = "Account Report"
    _rec_name = 'name'

    @api.depends('parent_id', 'parent_id.level')
    def _get_level(self):
        """Returns a dictionary with key=the ID of a record and
         value = the level of this
           record in the tree structure."""
        for report in self:
            level = 0
            if report.parent_id:
                level = report.parent_id.level + 1
            report.level = level

    def _get_children_by_order(self):
        """returns a recordset of all the children computed recursively,
         and sorted by sequence. Ready for the printing"""
        res = self
        children = self.search([('parent_id', 'in', self.ids)],
                               order='sequence ASC')
        if children:
            for child in children:
                res += child._get_children_by_order()
        return res

    name = fields.Char('Report Name', required=True, translate=True)
    parent_id = fields.Many2one('account.financial.report', 'Parent')
    children_ids = fields.One2many(
        'account.financial.report',
        'parent_id',
        'Account Report')
    sequence = fields.Integer('Sequence')
    level = fields.Integer(compute='_get_level', string='Level', store=True, recursive=True)
    type = fields.Selection(
        [('sum', 'View'),
         ('accounts', 'Accounts'),
         ('account_type', 'Account Type'),
         ('account_report', 'Report Value')],
        'Type',
        default='sum')
    account_ids = fields.Many2many(
        'account.account',
        'account_account_financial_report',
        'report_line_id',
        'account_id',
        'Accounts')
    account_report_id = fields.Many2one(
        'account.financial.report',
        'Report Value')
    account_type_ids = fields.Selection(
        selection=[
            ("asset_receivable", "Receivable"),
            ("asset_cash", "Bank and Cash"),
            ("asset_current", "Current Assets"),
            ("asset_non_current", "Non-current Assets"),
            ("asset_prepayments", "Prepayments"),
            ("asset_fixed", "Fixed Assets"),
            ("liability_payable", "Payable"),
            ("liability_credit_card", "Credit Card"),
            ("liability_current", "Current Liabilities"),
            ("liability_non_current", "Non-current Liabilities"),
            ("equity", "Equity"),
            ("equity_unaffected", "Current Year Earnings"),
            ("income", "Income"),
            ("income_other", "Other Income"),
            ("expense", "Expenses"),
            ("expense_depreciation", "Depreciation"),
            ("expense_direct_cost", "Cost of Revenue"),
            ("off_balance", "Off-Balance Sheet"),
        ],
        string="Account Type",
        help="These types are defined according to your country. The type contains more information " \
             "about the account and its specificities."
    )

    sign = fields.Selection(
        [("-1", 'Reverse balance sign'), ("1", 'Preserve balance sign')],
        'Sign on Reports', required=True, default="1",
        help='For accounts that are typically more'
             ' debited than credited and that you'
             ' would like to print as negative'
             ' amounts in your reports, you should'
             ' reverse the sign of the balance;'
             ' e.g.: Expense account. The same applies'
             ' for accounts that are typically more'
             ' credited than debited and that you would'
             ' like to print as positive amounts in'
             ' your reports; e.g.: Income account.')
    display_detail = fields.Selection(
        [('no_detail', 'No detail'),
         ('detail_flat', 'Display children flat'),
         ('detail_with_hierarchy', 'Display children with hierarchy')],
        'Display details',
        default='detail_flat')
    style_overwrite = fields.Selection(
        [('0', 'Automatic formatting'),
         ('1', 'Main Title 1 (bold, underlined)'),
         ('2', 'Title 2 (bold)'),
         ('3', 'Title 3 (bold, smaller)'),
         ('4', 'Normal Text'),
         ('5', 'Italic Text (smaller)'),
         ('6', 'Smallest Text')],
        'Financial Report Style',
        default='0',
        help="You can set up here the format you want this"
             " record to be displayed. If you leave the"
             " automatic formatting, it will be computed"
             " based on the financial reports hierarchy "
             "(auto-computed field 'level').")

    @api.model
    def _fix_financial_report_data(self):
        """Fix financial report data for existing records.

        Since the XML data files have noupdate="1", existing records won't be
        updated on module upgrade. This method ensures:
        1. Equity accounts exist in the chart of accounts.
        2. The Owner's Equity section exists under Balance Sheet.
        3. "Profit (Loss) to report" is under Equity, not Liability.
        """
        # ------------------------------------------------------------------
        # 1. Ensure equity accounts exist (noupdate="1" skips them on update)
        # ------------------------------------------------------------------
        equity_accounts = [
            ('4001', '实收资本', 'equity'),
            ('4101', '资本公积', 'equity'),
            ('4102', '盈余公积', 'equity'),
            ('4104', '利润分配——未分配利润', 'equity'),
        ]
        AccountAccount = self.env['account.account']
        for code, name, account_type in equity_accounts:
            existing = AccountAccount.search(
                [('code', '=', code)], limit=1)
            if not existing:
                AccountAccount.create({
                    'code': code,
                    'name': name,
                    'account_type': account_type,
                })

        # ------------------------------------------------------------------
        # 2. Ensure Owner's Equity section in Balance Sheet
        # ------------------------------------------------------------------
        balance_sheet = self.env.ref(
            'tour_accounting.account_financial_report_balancesheet0',
            raise_if_not_found=False)
        liability_sum = self.env.ref(
            'tour_accounting.account_financial_report_liabilitysum0',
            raise_if_not_found=False)
        profit_loss_report = self.env.ref(
            'tour_accounting.account_financial_report_profitloss_toreport0',
            raise_if_not_found=False)
        pnl_report = self.env.ref(
            'tour_accounting.account_financial_report_profitandloss0',
            raise_if_not_found=False)

        if not all([balance_sheet, liability_sum, profit_loss_report, pnl_report]):
            return True

        # Ensure equity sum section exists
        equity_sum = self.env.ref(
            'tour_accounting.account_financial_report_equity_sum0',
            raise_if_not_found=False)
        if not equity_sum and balance_sheet:
            equity_sum = self.create({
                'name': '所有者权益',
                'sequence': 2,
                'parent_id': balance_sheet.id,
                'display_detail': 'no_detail',
                'type': 'sum',
            })

        # Ensure equity leaf exists
        if equity_sum:
            equity_leaf = self.env.ref(
                'tour_accounting.account_financial_report_equity0',
                raise_if_not_found=False)
            if not equity_leaf:
                self.create({
                    'name': '权益',
                    'parent_id': equity_sum.id,
                    'display_detail': 'detail_with_hierarchy',
                    'type': 'account_type',
                    'account_type_ids': 'equity',
                })

        # ------------------------------------------------------------------
        # 3. Move "Profit (Loss) to report" from liability to equity
        # ------------------------------------------------------------------
        if profit_loss_report.parent_id.id != equity_sum.id:
            profit_loss_report.write({'parent_id': equity_sum.id})

        return True

    @api.model
    def _fix_cash_flow_report_data(self):
        """Fix cash flow report data for existing records.

        Changes the type from 'accounts' to 'account_type' and sets the
        account_type_ids for each cash flow leaf item.
        """
        cash_flow_items = {
            'tour_accounting.cash_in_from_operation0': 'asset_cash',
            'tour_accounting.cash_out_operation1': 'expense',
            'tour_accounting.cash_in_investing0': 'asset_non_current',
            'tour_accounting.cash_out_investing1': 'asset_fixed',
            'tour_accounting.cash_in_financial0': 'equity',
            'tour_accounting.cash_out_financial1': 'liability_non_current',
        }
        for xml_id, account_type in cash_flow_items.items():
            report = self.env.ref(xml_id, raise_if_not_found=False)
            if report:
                if report.type != 'account_type':
                    report.write({'type': 'account_type'})
                if report.account_type_ids != account_type:
                    report.write({'account_type_ids': account_type})

        return True
