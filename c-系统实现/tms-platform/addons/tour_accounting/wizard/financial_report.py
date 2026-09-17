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
import re
from odoo import api, models, fields


class FinancialReport(models.TransientModel):
    _name = "financial.report"
    _inherit = "account.common.report"
    _description = "Financial Reports"

    name = fields.Char(string="Financial Report", default="Financial Report", required=True, translate=True)

    view_format = fields.Selection([
        ('vertical', 'Vertical'),
        ('horizontal', 'Horizontal')],
        default='vertical',
        string="Format")


    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        return result

    @api.model
    def _get_account_report(self):
        reports = []
        if self.env.context.get('active_id'):
            menu = self.env['ir.ui.menu'].browse(
                self.env.context.get('active_id')).name
            reports = self.env['account.financial.report'].search([
                ('name', 'ilike', menu)])
        return reports and reports[0] or False

    enable_filter = fields.Boolean(
        string='Enable Comparison',
        default=False)
    account_report_id = fields.Many2one(
        'account.financial.report',
        string='Account Reports',
        required=True)

    debit_credit = fields.Boolean(
        string='Display Debit/Credit Columns',
        default=True,
        help="This option allows you to"
             " get more details about the "
             "way your balances are computed."
             " Because it is space consuming,"
             " we do not allow to use it "
             "while doing a comparison.")

    def view_report_pdf(self):
        """This function will be executed when we click the view button
        from the wizard. Based on the values provided in the wizard, this
        function will print pdf report"""
        self.ensure_one()
        data = dict()
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'enable_filter', 'debit_credit', 'date_to',
             'account_report_id', 'target_move', 'view_format',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')

        report_lines = self.get_account_lines(data['form'])
        # find the journal items of these accounts
        journal_items = self.find_journal_items(report_lines, data['form'])

        def set_report_level(rec):
            """This function is used to set the level of each item.
            This level will be used to set the alignment in the dynamic reports."""
            level = 1
            if not rec['parent']:
                return level
            else:
                for line in report_lines:
                    key = 'a_id' if line['type'] == 'account' else 'id'
                    if line[key] == rec['parent']:
                        return level + set_report_level(line)

        # finding the root
        for item in report_lines:
            item['balance'] = round(item['balance'], 2)
            if not item['parent']:
                item['level'] = 1
                parent = item
                report_name = item['name']
                id = item['id']
                report_id = item['r_id']
            else:
                item['level'] = set_report_level(item)
        currency = self._get_currency()
        data['currency'] = currency
        data['journal_items'] = journal_items
        data['report_lines'] = report_lines
        # checking view type
        return self.env.ref(
            'tour_accounting.financial_report_pdf').report_action(self,
                                                                      data)

    def _financial_report_data(self):
        """Build the ``data`` dict used by both the PDF and xlsx exports."""
        data = dict()
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'enable_filter', 'debit_credit', 'date_to',
             'account_report_id', 'target_move', 'view_format',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')
        return data

    def action_print_xlsx(self):
        """Export the financial report (P&L / Balance Sheet) to xlsx."""
        self.ensure_one()
        data = self._financial_report_data()
        report_lines = self.get_account_lines(data['form'])
        columns = [{'label': 'Name', 'width': 45}]
        if self.debit_credit:
            columns += [{'label': 'Debit', 'width': 18, 'num': True},
                        {'label': 'Credit', 'width': 18, 'num': True}]
        columns.append({'label': 'Balance', 'width': 18, 'num': True})
        if self.enable_filter:
            columns.append(
                {'label': 'Comparison', 'width': 18, 'num': True})
        rows = []
        for line in report_lines:
            is_report = line.get('type') == 'report'
            cells = [line.get('name')]
            if self.debit_credit:
                cells += [line.get('debit', 0.0), line.get('credit', 0.0)]
            cells.append(line.get('balance', 0.0))
            if self.enable_filter:
                cells.append(line.get('balance_cmp', 0.0))
            rows.append({
                'cells': cells,
                'bold': is_report,
                'indent': 0 if is_report else 1,
            })
        table = {
            'title': self.account_report_id.name or 'Financial Report',
            'meta': self._xlsx_meta(data['form']),
            'columns': columns,
            'rows': rows,
        }
        return self._xlsx_action(
            self.account_report_id.name or 'Financial Report', table)

    def action_view_report(self):
        """Open the financial report in an online OWL-based viewer."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'tour_accounting.financial_report',
            'params': {
                'wizard_model': 'financial.report',
                'wizard_id': self.id,
                'period_id': self.period_id.id if self.period_id else False,
            },
            'name': self.account_report_id.name or 'Financial Report',
        }

    def _compute_account_balance(self, accounts):
        """ compute the balance, debit
        and credit for the provided accounts
        """
        mapping = {
            'balance':
                "COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0)"
                " as balance",
            'debit': "COALESCE(SUM(debit), 0) as debit",
            'credit': "COALESCE(SUM(credit), 0) as credit",
        }

        res = {}
        for account in accounts:
            res[account.id] = dict((fn, 0.0)
                                   for fn in mapping.keys())
        if accounts:
            tables, where_clause, where_params = (
                self.env['account.move.line']._query_get())
            tables = tables.replace(
                '"', '') if tables else "account_move_line"
            wheres = [""]
            if where_clause.strip():
                wheres.append(where_clause.strip())
            filters = " AND ".join(wheres)
            request = ("SELECT account_id as id, " +
                       ', '.join(mapping.values()) +
                       " FROM " + tables +
                       " WHERE account_id IN %s " +
                       filters +
                       " GROUP BY account_id")
            params = (tuple(accounts._ids),) + tuple(where_params)
            self.env.cr.execute(request, params)
            for row in self.env.cr.dictfetchall():
                res[row['id']] = row
        return res

    def _compute_report_balance(self, reports):
        """returns a dictionary with key=the ID of a record and
         value=the credit, debit and balance amount
        computed for this record. If the record is of type :
        'accounts' : it's the sum of the linked accounts
        'account_type' : it's the sum of leaf accounts with
         such an account_type
        'account_report' : it's the amount of the related report
        'sum' : it's the sum of the children of this record
         (aka a 'view' record)"""
        res = {}
        fields = ['credit', 'debit', 'balance']
        for report in reports:
            if report.id in res:
                continue
            res[report.id] = dict((fn, 0.0) for fn in fields)
            if report.type == 'accounts':
                # it's the sum of the linked accounts
                res[report.id]['account'] = self._compute_account_balance(
                    report.account_ids
                )
                for value in \
                        res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_type':
                # it's the sum the leaf accounts
                #  with such an account type
                # Use XML ID to identify reports that need multiple account
                # types, so the logic works regardless of UI language.
                multi_type_map = {
                    'tour_accounting.account_financial_report_expense0': [
                        'expense', 'expense_depreciation',
                        'expense_direct_cost',
                    ],
                    'tour_accounting.account_financial_report_liability0': [
                        'liability_payable', 'liability_credit_card',
                        'liability_current', 'liability_non_current',
                    ],
                    'tour_accounting.account_financial_report_assets0': [
                        'asset_receivable', 'asset_cash', 'asset_current',
                        'asset_non_current', 'asset_prepayments',
                        'asset_fixed',
                    ],
                }
                account_types = None
                for xml_id, types in multi_type_map.items():
                    try:
                        if report == self.env.ref(xml_id):
                            account_types = types
                            break
                    except ValueError:
                        continue
                if account_types:
                    accounts = self.env['account.account'].search([
                        ('account_type', 'in', account_types),
                    ])
                else:
                    accounts = self.env['account.account'].search([
                        ('account_type', '=', report.account_type_ids),
                    ])

                res[report.id]['account'] = self._compute_account_balance(
                    accounts)

                for value in res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_report' and report.account_report_id:
                # it's the amount of the linked report
                res2 = self._compute_report_balance(report.account_report_id)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
            elif report.type == 'sum':
                # it's the sum of the children of this account.report
                res2 = self._compute_report_balance(report.children_ids)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
        return res

    def get_account_lines(self, data):
        lines = []
        account_report = self.env['account.financial.report'].search([
            ('id', '=', data['account_report_id'][0])
        ])
        child_reports = account_report._get_children_by_order()
        res = self.with_context(
            data.get('used_context'))._compute_report_balance(child_reports)
        if data['enable_filter']:
            comparison_res = self._compute_report_balance(child_reports)
            for report_id, value in comparison_res.items():
                res[report_id]['comp_bal'] = value['balance']
                report_acc = res[report_id].get('account')
                if report_acc:
                    for account_id, val in \
                            comparison_res[report_id].get('account').items():
                        report_acc[account_id]['comp_bal'] = val['balance']

        for report in child_reports:
            r_name = str(report.name)
            r_name = re.sub('[^0-9a-zA-Z]+', '', r_name)
            if report.parent_id:
                p_name = str(report.parent_id.name)
                p_name = re.sub('[^0-9a-zA-Z]+', '', p_name) + str(
                    report.parent_id.id)
            else:
                p_name = False
            vals = {
                'r_id': report.id,
                'id': r_name + str(report.id),
                'sequence': report.sequence,
                'parent': p_name,
                'name': report.name,
                'balance': res[report.id]['balance'] * int(report.sign),
                'type': 'report',
                'level': bool(
                    report.style_overwrite) and report.style_overwrite or
                         report.level,
                'account_type': report.type or False,
                # used to underline the financial report balances
            }
            if data['debit_credit']:
                vals['debit'] = res[report.id]['debit']
                vals['credit'] = res[report.id]['credit']

            if data['enable_filter']:
                vals['balance_cmp'] = res[report.id]['comp_bal'] * int(
                    report.sign)

            lines.append(vals)
            if report.display_detail == 'no_detail':
                # the rest of the loop is
                # used to display the details of the
                #  financial report, so it's not needed here.
                continue

            if res[report.id].get('account'):
                sub_lines = []
                for account_id, value \
                        in res[report.id]['account'].items():
                    # if there are accounts to display,
                    #  we add them to the lines with a level equals
                    #  to their level in
                    # the COA + 1 (to avoid having them with a too low level
                    #  that would conflicts with the level of data
                    # financial reports for Assets, liabilities...)
                    flag = False
                    account = self.env['account.account'].browse(account_id)
                    # new_r_name = str(report.name)
                    # new_r_name = new_r_name.replace(" ", "-") + "-"
                    acct_code = account.code or ''
                    vals = {
                        'account': account.id,
                        'a_id': acct_code + re.sub('[^0-9a-zA-Z]+', 'acnt',
                                                      account.name) + str(
                            account.id),
                        'name': acct_code + '-' + account.name,
                        'balance': value['balance'] * int(report.sign) or 0.0,
                        'type': 'account',
                        'parent': r_name + str(report.id),
                        'level': (
                                report.display_detail == 'detail_with_hierarchy' and
                                4),
                        'account_type': account.account_type,
                    }
                    if data['debit_credit']:
                        vals['debit'] = value['debit']
                        vals['credit'] = value['credit']
                        for company in account.company_ids:
                            if not company.currency_id.is_zero(
                                    vals['debit']) or \
                                    not company.currency_id.is_zero(
                                        vals['credit']):
                                flag = True
                    for company in account.company_ids:
                        if not company.currency_id.is_zero(
                                vals['balance']):
                            flag = True
                    if data['enable_filter']:
                        vals['balance_cmp'] = value['comp_bal'] * int(
                            report.sign)
                        for company in account.company_ids:
                            if not company.currency_id.is_zero(
                                    vals['balance_cmp']):
                                flag = True
                    if flag:
                        sub_lines.append(vals)
                lines += sorted(sub_lines,
                                key=lambda sub_line: sub_line['name'])
        return lines

    def find_journal_items(self, report_lines, form):
        cr = self.env.cr
        journal_items = []
        for i in report_lines:
            if i['type'] == 'account':
                account = i['account']
                if form['target_move'] == 'posted':
                    search_query = ("select aml.id, am.id as j_id, "
                                    "aml.account_id, aml.date, aml.name as "
                                    "label, am.name, (aml.debit-aml.credit) as "
                                    "balance, aml.debit, aml.credit, "
                                    "aml.partner_id  from "
                                    "account_move_line aml "
                                    "join account_move am on (aml.move_id=am.id"
                                    " and am.state=%s) where aml.account_id=%s")
                    vals = [form['target_move']]
                else:
                    search_query = ("select aml.id, am.id as j_id, "
                                    "aml.account_id, aml.date, aml.name as "
                                    "label, am.name, (aml.debit-aml.credit) as "
                                    "balance, aml.debit, aml.credit, "
                                    "aml.partner_id from account_move_line aml"
                                    " join account_move am on "
                                    "(aml.move_id=am.id) where "
                                    "aml.account_id=%s")
                    vals = []
                if form['date_from'] and form['date_to']:
                    search_query += " and aml.date>=%s and aml.date<=%s"
                    vals += [account, form['date_from'], form['date_to']]
                elif form['date_from']:
                    search_query += " and aml.date>=%s"
                    vals += [account, form['date_from']]
                elif form['date_to']:
                    search_query += " and aml.date<=%s"
                    vals += [account, form['date_to']]
                else:
                    vals += [account]
                cr.execute(search_query, tuple(vals))
                items = cr.dictfetchall()

                for j in items:
                    temp = j['id']
                    j['id'] = re.sub('[^0-9a-zA-Z]+', '', i['name']) + str(
                        temp)
                    j['p_id'] = str(i['a_id'])
                    j['type'] = 'journal_item'
                    journal_items.append(j)
        return journal_items

    @api.model
    def _get_currency(self):
        journal = self.env['account.journal'].browse(
            self.env.context.get('default_journal_id', False))
        if journal.currency_id:
            return journal.currency_id.id
        return self.env.company.currency_id.symbol

    # ------------------------------------------------------------------
    # Online report viewer support
    # ------------------------------------------------------------------
    @api.model
    def get_online_report_data(self, wizard_id, period_id=None,
                               date_from=None, date_to=None):
        """Return report data as JSON-serializable dict for the OWL viewer.

        ``period_id`` takes precedence over explicit ``date_from``/``date_to``
        values: when provided the date range is read from the period record.
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

        data = dict()
        data['ids'] = []
        data['model'] = 'financial.report'
        data['form'] = wizard.read(
            ['date_from', 'enable_filter', 'debit_credit', 'date_to',
             'account_report_id', 'target_move', 'view_format',
             'company_id'])[0]

        used_context = wizard._build_contexts(data)
        if date_from:
            used_context['date_from'] = date_from
        if date_to:
            used_context['date_to'] = date_to
        used_context['strict_range'] = True if used_context.get('date_from') else False

        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')

        report_lines = wizard.get_account_lines(data['form'])

        # Build tree structure for the OWL viewer
        tree, all_ids = self._build_report_tree(report_lines)

        # Compute totals
        total_debit = sum(l.get('debit', 0) for l in report_lines if l['type'] == 'account')
        total_credit = sum(l.get('credit', 0) for l in report_lines if l['type'] == 'account')
        total_balance = sum(l.get('balance', 0) for l in report_lines if l['type'] == 'account')

        return {
            'tree': tree,
            'expanded_rows': all_ids,
            'show_debit_credit': data['form'].get('debit_credit', True),
            'currency': self.env.company.currency_id.id,
            'report_name': wizard.account_report_id.name,
            'total_debit': round(total_debit, 2),
            'total_credit': round(total_credit, 2),
            'total_balance': round(total_balance, 2),
        }

    @api.model
    def _build_report_tree(self, report_lines):
        """Convert flat report lines into a tree structure for the OWL viewer.

        The flat list from ``get_account_lines`` contains report-type lines
        (section headers) and account-type lines (detail rows).  The
        hierarchy is defined by the ``parent`` key on each line, not by the
        ``level`` field (which is unreliable for report-type lines due to
        ``style_overwrite`` being the string ``'0'``).
        """
        # Phase 1: Create a node for every line, indexed by its unique key
        node_map = {}  # key -> node dict
        ordered_keys = []  # preserve document order

        for idx, line in enumerate(report_lines):
            is_report = line['type'] == 'report'
            is_account = line['type'] == 'account'
            if is_report:
                # Report lines have unique ids (e.g. 'Expense7')
                node_key = line.get('id') or ('rpt_%d' % idx)
            else:
                # Account lines may share the same a_id across sections,
                # so append the index to guarantee uniqueness.
                base_key = line.get('a_id') or ('acct_%d' % idx)
                node_key = '%s__%d' % (base_key, idx)

            node = {
                'id': node_key,
                'name': line.get('name', ''),
                'debit': round(line.get('debit', 0), 2),
                'credit': round(line.get('credit', 0), 2),
                'balance': round(line.get('balance', 0), 2),
                'account_id': line.get('account') if is_account else False,
                'report_id': line.get('r_id') if is_report else False,
                'is_report': is_report,
                'has_children': False,
                'children': [],
                '_parent_key': line.get('parent'),
                '_display_level': 0,
            }
            node_map[node_key] = node
            ordered_keys.append(node_key)

        # Phase 2: Wire parent → children using the ``parent`` key
        root_keys = []
        for key in ordered_keys:
            node = node_map[key]
            parent_key = node.pop('_parent_key', None)
            if parent_key and parent_key in node_map:
                parent = node_map[parent_key]
                parent['has_children'] = True
                parent['children'].append(node)
            else:
                root_keys.append(key)

        # Phase 3: Compute display levels from tree depth
        all_ids = []

        def set_depth(nodes, depth):
            for n in nodes:
                n['level'] = depth
                all_ids.append(n['id'])
                if n['children']:
                    set_depth(n['children'], depth + 1)

        roots = [node_map[k] for k in root_keys]
        set_depth(roots, 0)

        return roots, all_ids

    @api.model
    def get_drilldown_action(self, account_id=False, report_id=False,
                             period_id=None, date_from=None, date_to=None):
        """Return an action dict to drill down into journal items."""
        # Resolve period to date range
        if period_id:
            period = self.env['tour.account.period'].browse(int(period_id))
            if period.exists():
                date_from = str(period.date_start)
                date_to = str(period.date_end)

        domain = [('display_type', 'not in', ['line_note', 'line_section'])]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        if account_id:
            account = self.env['account.account'].browse(int(account_id))
            domain.append(('account_id', '=', int(account_id)))
            name = '%s - %s' % (account.code, account.name)
        elif report_id:
            account_ids = self._get_report_account_ids(int(report_id))
            if account_ids:
                domain.append(('account_id', 'in', account_ids))
            report = self.env['account.financial.report'].browse(int(report_id))
            name = report.name
        else:
            name = '凭证明细'

        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def _get_report_account_ids(self, report_id):
        """Recursively collect account IDs for a financial report node."""
        report = self.env['account.financial.report'].browse(report_id)
        if not report.exists():
            return []
        account_ids = set()
        if report.type == 'accounts':
            account_ids.update(report.account_ids.ids)
        elif report.type == 'account_type':
            if report.account_type_ids:
                accounts = self.env['account.account'].search([
                    ('account_type', '=', report.account_type_ids),
                ])
                account_ids.update(accounts.ids)
        for child in report.children_ids:
            account_ids.update(self._get_report_account_ids(child.id))
        return list(account_ids)


class ProfitLossPdf(models.AbstractModel):
    """ Abstract model for generating PDF report value and send to template """

    _name = 'report.tour_accounting.report_financial'
    _description = 'Financial Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        """ Provide report values to template """
        ctx = {
            'data': data,
            'journal_items': data['journal_items'],
            'report_lines': data['report_lines'],
            'account_report': data['form']['account_report_id'][1],
            'currency': data['currency'],
        }
        return ctx
