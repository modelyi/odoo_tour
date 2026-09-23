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
            ("income_non_operating", "Non-operating Income"),
            ("expense", "Expenses"),
            ("expense_depreciation", "Depreciation"),
            ("expense_direct_cost", "Cost of Revenue"),
            ("expense_tax", "Tax & Surcharges"),
            ("expense_selling", "Selling Expenses"),
            ("expense_admin", "Administrative Expenses"),
            ("expense_finance", "Financial Expenses"),
            ("expense_non_operating", "Non-operating Expenses"),
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
        1. Old report nodes are cleaned up.
        2. Equity section exists under Balance Sheet.
        3. "本年利润" is under Equity.
        """
        # Clean up old report nodes that no longer exist in XML
        old_xml_ids = [
            'tour_accounting.account_financial_report_assets0',
            'tour_accounting.account_financial_report_liabilitysum0',
            'tour_accounting.account_financial_report_liability0',
            'tour_accounting.financial_report_gross_profit',
            'tour_accounting.financial_report_cost_of_revenue',
            'tour_accounting.account_financial_report_operating_income0',
            'tour_accounting.account_financial_report_income0',
            'tour_accounting.account_financial_report_other_income0',
            'tour_accounting.account_financial_report_expense0',
        ]
        for xml_id in old_xml_ids:
            record = self.env.ref(xml_id, raise_if_not_found=False)
            if record:
                record.unlink()

        # Ensure equity section exists
        balance_sheet = self.env.ref(
            'tour_accounting.account_financial_report_balancesheet0',
            raise_if_not_found=False)
        profit_loss_report = self.env.ref(
            'tour_accounting.account_financial_report_profitloss_toreport0',
            raise_if_not_found=False)
        equity_sum = self.env.ref(
            'tour_accounting.account_financial_report_equity_sum0',
            raise_if_not_found=False)

        if not all([balance_sheet, equity_sum]):
            return True

        if profit_loss_report and profit_loss_report.parent_id.id != equity_sum.id:
            profit_loss_report.write({'parent_id': equity_sum.id})

        # 清理无任何 ir.model.data 引用的旧版脚本产物（重复的英文报表树）
        tracked = set(self.env['ir.model.data'].search([
            ('model', '=', 'account.financial.report')]).mapped('res_id'))
        stale_ids = [r.id for r in self.search([]) if r.id not in tracked]
        if stale_ids:
            self.browse(stale_ids).unlink()

        # 根节点中英文名对齐数据文件（历史英文名/核心旧译名残留）
        installed = {code for code, _ in self.env['res.lang'].get_installed()}
        for xml_id, cn_name in [
            ('account_financial_report_profitandloss0', '利润表'),
            ('account_financial_report_balancesheet0', '资产负债表'),
            ('account_financial_report_cash_flow0', '现金流量表'),
        ]:
            rec = self.env.ref('tour_accounting.' + xml_id,
                               raise_if_not_found=False)
            if rec:
                rec.write({'name': cn_name})
                # 20 空库默认不装 zh_CN，对未安装语言 write 会 UserError
                if 'zh_CN' in installed:
                    rec.with_context(lang='zh_CN').write({'name': cn_name})

        return True

    @api.model
    def _fix_cash_flow_report_data(self):
        """Fix cash flow report data for existing records.

        Clean up old leaf nodes that no longer exist in the simplified XML.
        The actual cash flow lines are now computed in Python.
        """
        old_leaf_ids = [
            'tour_accounting.cash_in_from_operation0',
            'tour_accounting.cash_out_operation1',
            'tour_accounting.cash_in_investing0',
            'tour_accounting.cash_out_investing1',
            'tour_accounting.cash_in_financial0',
            'tour_accounting.cash_out_financial1',
        ]
        for xml_id in old_leaf_ids:
            record = self.env.ref(xml_id, raise_if_not_found=False)
            if record:
                record.unlink()
        return True
