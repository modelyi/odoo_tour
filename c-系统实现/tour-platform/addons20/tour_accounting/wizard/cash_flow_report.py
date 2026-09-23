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


class AccountingReport(models.TransientModel):
    _name = "cash.flow.report"
    _inherit = "account.common.report"
    _description = "Cash Flow Report"

    name = fields.Char(string="Cash Flow Report", default="Cash Flow Report", required=True, translate=True)

    @api.model
    def _get_account_report(self):
        reports = []
        if self.env.context.get('active_id'):
            menu = self.env['ir.ui.menu'].browse(
                self.env.context.get('active_id')).name
            reports = self.env['account.financial.report'].search(
                [('name', 'ilike', menu)])
        return reports and reports[0] or False

    enable_filter = fields.Boolean(string='Enable Comparison')
    account_report_id = fields.Many2one('account.financial.report',
                                        string='Account Reports',
                                        required=True,
                                        default=_get_account_report)
    label_filter = fields.Char(string='Column Label',
                               help="This label will be displayed on report to show the balance"
                                    " computed for the given comparison filter.")
    filter_cmp = fields.Selection(
        [('filter_no', 'No Filters'), ('filter_date', 'Date')],
        string='Filter by', required=True, default='filter_no')
    date_from_cmp = fields.Date(string='Date Start')
    date_to_cmp = fields.Date(string='Date End')
    debit_credit = fields.Boolean(string='Display Debit/Credit Columns',
                                  help="This option allows you to get more details about the way your balances are computed. Because it is space consuming, we do not allow to use it while doing a comparison.")

    def _build_comparison_context(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        if data['form']['filter_cmp'] == 'filter_date':
            result['date_from'] = data['form']['date_from_cmp']
            result['date_to'] = data['form']['date_to_cmp']
            result['strict_range'] = True
        return result

    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form']['journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form']['target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        result['company_id'] = data['form']['company_id'][0] or False
        return result

    def check_report(self):
        res = super().check_report()
        data = {}
        data['form'] = self.read(
            ['account_report_id', 'date_from_cmp', 'date_to_cmp',
             'journal_ids', 'filter_cmp', 'target_move'])[0]
        for field in ['account_report_id']:
            if isinstance(data['form'][field], tuple):
                data['form'][field] = data['form'][field][0]
        comparison_context = self._build_comparison_context(data)
        res['data']['form']['comparison_context'] = comparison_context
        return res

    def _print_report(self, data):
        data['form'].update(self.read(
            ['date_from_cmp', 'debit_credit', 'date_to_cmp', 'filter_cmp',
             'account_report_id', 'enable_filter', 'label_filter',
             'target_move'])[0])
        return self.env.ref(
            'tour_accounting.action_report_cash_flow').report_action(self,
                                                                         data=data,
                                                                         config=False)

    def action_print_xlsx(self):
        """Export the cash flow statement to xlsx."""
        self.ensure_one()
        data = self._xlsx_base_data()
        data['form'].update(self.read(
            ['date_from_cmp', 'debit_credit', 'date_to_cmp', 'filter_cmp',
             'account_report_id', 'enable_filter', 'label_filter',
             'target_move'])[0])
        data['form']['comparison_context'] = self._build_comparison_context(
            data)
        report_lines = self.env[
            'report.tour_accounting.report_cash_flow'].get_account_lines(
            data['form'])
        columns = [{'label': 'Name', 'width': 45}]
        if self.debit_credit:
            columns += [{'label': 'Debit', 'width': 18, 'num': True},
                        {'label': 'Credit', 'width': 18, 'num': True}]
        columns.append({'label': 'Balance', 'width': 18, 'num': True})
        if self.enable_filter:
            columns.append(
                {'label': self.label_filter or 'Comparison', 'width': 18,
                 'num': True})
        rows = []
        for line in report_lines:
            is_report = line.get('type') == 'report'
            cells = [line.get('name')]
            if self.debit_credit:
                cells += [line.get('debit', 0.0), line.get('credit', 0.0)]
            cells.append(line.get('balance', 0.0))
            if self.enable_filter:
                cells.append(line.get('balance_cmp', 0.0))
            rows.append({'cells': cells, 'bold': is_report,
                         'indent': 0 if is_report else 1})
        table = {
            'title': 'Cash Flow Report',
            'meta': self._xlsx_meta(data['form']),
            'columns': columns,
            'rows': rows,
        }
        return self._xlsx_action('Cash Flow Report', table)

    # ------------------------------------------------------------------
    # Online report viewer support
    # ------------------------------------------------------------------
    def action_view_report(self):
        """Open the cash flow report in an online OWL-based viewer."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'tour_accounting.financial_report',
            'params': {
                'wizard_model': 'cash.flow.report',
                'wizard_id': self.id,
                'period_id': self.period_id.id if self.period_id else False,
            },
            'name': '现金流量表',
        }

    @api.model
    def get_online_report_data(self, wizard_id, period_id=None,
                               date_from=None, date_to=None):
        """Return cash flow report data as JSON-serializable dict.

        ``period_id`` takes precedence over explicit date parameters.
        """
        wizard = self.browse(wizard_id)
        if not wizard.exists():
            return {'error': 'Wizard record not found'}

        # Resolve period to date range
        if period_id:
            period = self.env['tour.account.period'].browse(int(period_id))
            if period.exists():
                date_from = str(period.date_start)
                date_to = str(period.date_end)

        data = {}
        data['ids'] = []
        data['model'] = 'cash.flow.report'
        data['form'] = wizard.read(
            ['account_report_id', 'date_from_cmp', 'debit_credit',
             'date_to_cmp', 'filter_cmp', 'target_move',
             'enable_filter', 'label_filter'])[0]

        used_context = wizard._build_contexts({
            'form': {
                'journal_ids': wizard.journal_ids.ids,
                'target_move': wizard.target_move,
                'date_from': date_from or wizard.date_from,
                'date_to': date_to or wizard.date_to,
                'company_id': (wizard.company_id.id, wizard.company_id.name),
            }
        })
        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')

        report_lines = self.env[
            'report.tour_accounting.report_cash_flow'].get_account_lines(
            data['form'])

        # Reuse the tree builder from financial.report
        tree, all_ids = self.env['financial.report']._build_report_tree(
            report_lines)

        total_debit = sum(
            l.get('debit', 0) for l in report_lines if l['type'] == 'account')
        total_credit = sum(
            l.get('credit', 0) for l in report_lines if l['type'] == 'account')
        total_balance = sum(
            l.get('balance', 0) for l in report_lines if l['type'] == 'account')

        return {
            'tree': tree,
            'expanded_rows': all_ids,
            'show_debit_credit': data['form'].get('debit_credit', True),
            'currency': self.env.company.currency_id.id,
            'report_name': '现金流量表',
            'total_debit': round(total_debit, 2),
            'total_credit': round(total_credit, 2),
            'total_balance': round(total_balance, 2),
        }
