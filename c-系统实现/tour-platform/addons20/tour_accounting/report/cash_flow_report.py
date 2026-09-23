# -*- coding: utf-8 -*-
#############################################################################
#
#    TMS Cash Flow Report - Direct Method (财政部标准格式)
#    基于会计分录的现金流量分析（直接法）
#    对齐《企业会计准则第31号——现金流量表》
#
#############################################################################
import time
from odoo import api, models, _
from odoo.exceptions import UserError


class ReportCashFlow(models.AbstractModel):
    _name = 'report.tour_accounting.report_cash_flow'
    _description = 'Cash Flow Report (Direct Method - MOF Standard)'

    CASH_ACCOUNT_TYPES = ['asset_cash', 'asset_current']

    def _get_cash_accounts(self):
        return self.env['account.account'].search([
            ('account_type', 'in', self.CASH_ACCOUNT_TYPES),
        ])

    def _get_opening_cash_balance(self, date_from):
        """计算期初现金及现金等价物余额"""
        cash_accounts = self._get_cash_accounts()
        if not cash_accounts:
            return 0.0
        tables, where_clause, where_params = (
            self.env['account.move.line']._query_get())
        tables = tables.replace('"', '') if tables else "account_move_line"
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        request = (
            "SELECT COALESCE(SUM(debit - credit), 0) "
            "FROM " + tables +
            " WHERE account_id IN %s " + filters +
            " AND date < %s"
        )
        params = (tuple(cash_accounts.ids),) + tuple(where_params) + (date_from,)
        self.env.cr.execute(request, params)
        return self.env.cr.fetchone()[0] or 0.0

    def _classify_cash_flow(self, cash_line, counterpart_line):
        """
        根据对方科目分类现金流量（财政部标准行项目）

        Returns:
            dict: {'section': 'operating/investing/financing',
                   'line_name': str,
                   'direction': 'in/out',
                   'amount': float}
        """
        cash_amount = cash_line.debit - cash_line.credit
        if cash_amount == 0:
            return None

        cp = counterpart_line.account_id
        cp_type = cp.account_type
        cp_code = cp.code or ''

        # === 经营活动 ===
        if cp_type in ('income', 'income_other'):
            return {
                'section': 'operating',
                'line_name': '销售商品、提供劳务收到的现金',
                'direction': 'in',
                'amount': abs(cash_amount),
            }

        if cp_type in ('expense_direct_cost',):
            return {
                'section': 'operating',
                'line_name': '购买商品、接受劳务支付的现金',
                'direction': 'out',
                'amount': abs(cash_amount),
            }

        if cp_type in ('expense', 'expense_depreciation'):
            return {
                'section': 'operating',
                'line_name': '支付其他与经营活动有关的现金',
                'direction': 'out',
                'amount': abs(cash_amount),
            }

        if cp_type == 'expense_tax':
            return {
                'section': 'operating',
                'line_name': '支付的各项税费',
                'direction': 'out',
                'amount': abs(cash_amount),
            }

        if cp_type in ('expense_selling', 'expense_admin'):
            return {
                'section': 'operating',
                'line_name': '支付其他与经营活动有关的现金',
                'direction': 'out',
                'amount': abs(cash_amount),
            }

        if cp_type == 'expense_finance':
            return {
                'section': 'operating',
                'line_name': '支付其他与经营活动有关的现金',
                'direction': 'out',
                'amount': abs(cash_amount),
            }

        if cp_type == 'expense_non_operating':
            return {
                'section': 'operating',
                'line_name': '支付其他与经营活动有关的现金',
                'direction': 'out',
                'amount': abs(cash_amount),
            }

        if cp_type == 'income_non_operating':
            return {
                'section': 'operating',
                'line_name': '收到其他与经营活动有关的现金',
                'direction': 'in',
                'amount': abs(cash_amount),
            }

        if cp_type == 'asset_receivable':
            if cash_amount > 0:
                return {
                    'section': 'operating',
                    'line_name': '销售商品、提供劳务收到的现金',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                }
            return None

        if cp_type == 'liability_payable':
            if cash_amount < 0:
                return {
                    'section': 'operating',
                    'line_name': '购买商品、接受劳务支付的现金',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                }
            if cash_amount > 0:
                return {
                    'section': 'operating',
                    'line_name': '收到其他与经营活动有关的现金',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                }
            return None

        if cp_type == 'liability_current':
            if cp_code.startswith('2211'):
                if cash_amount < 0:
                    return {
                        'section': 'operating',
                        'line_name': '支付给职工以及为职工支付的现金',
                        'direction': 'out',
                        'amount': abs(cash_amount),
                    }
                return None
            if cp_code.startswith('2221'):
                if cash_amount < 0:
                    return {
                        'section': 'operating',
                        'line_name': '支付的各项税费',
                        'direction': 'out',
                        'amount': abs(cash_amount),
                    }
                return None
            if cash_amount < 0:
                return {
                    'section': 'operating',
                    'line_name': '支付其他与经营活动有关的现金',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                }
            return None

        # === 投资活动 ===
        if cp_type in ('asset_fixed', 'asset_non_current'):
            if cash_amount < 0:
                return {
                    'section': 'investing',
                    'line_name': '购建固定资产等支付的现金',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                }
            else:
                return {
                    'section': 'investing',
                    'line_name': '处置固定资产等收到的现金净额',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                }

        # === 筹资活动 ===
        if cp_type == 'equity':
            if cash_amount > 0:
                return {
                    'section': 'financing',
                    'line_name': '吸收投资收到的现金',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                }
            else:
                return {
                    'section': 'financing',
                    'line_name': '分配股利、利润或偿付利息支付的现金',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                }

        if cp_type == 'liability_non_current':
            if cash_amount > 0:
                return {
                    'section': 'financing',
                    'line_name': '取得借款收到的现金',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                }
            else:
                return {
                    'section': 'financing',
                    'line_name': '偿还债务支付的现金',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                }

        return None

    def _compute_cash_flow(self, date_from, date_to):
        """计算期间内的现金流量，按财政部标准行项目汇总"""
        cash_accounts = self._get_cash_accounts()
        empty = self._empty_result()
        if not cash_accounts:
            return empty

        move_lines = self.env['account.move.line'].search([
            ('account_id', 'in', cash_accounts.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ])

        result = self._empty_result()

        for line in move_lines:
            counterpart_lines = line.move_id.line_ids.filtered(
                lambda l: l.account_id not in cash_accounts
            )
            for counterpart in counterpart_lines:
                classification = self._classify_cash_flow(line, counterpart)
                if classification:
                    section = classification['section']
                    direction = classification['direction']
                    amount = classification['amount']
                    line_name = classification['line_name']

                    result[section][direction] += amount
                    if line_name not in result[section]['items']:
                        result[section]['items'][line_name] = {
                            'in': 0.0, 'out': 0.0}
                    result[section]['items'][line_name][direction] += amount

        for section in ('operating', 'investing', 'financing'):
            result[section]['net'] = (
                result[section]['in'] - result[section]['out'])

        return result

    def _empty_result(self):
        return {
            'operating': {'in': 0, 'out': 0, 'net': 0, 'items': {}},
            'investing': {'in': 0, 'out': 0, 'net': 0, 'items': {}},
            'financing': {'in': 0, 'out': 0, 'net': 0, 'items': {}},
        }

    def get_account_lines(self, data):
        """生成财政部标准格式的现金流量表行数据"""
        context = data.get('used_context', {})
        date_from = context.get('date_from')
        date_to = context.get('date_to')
        if not date_from or not date_to:
            return []

        cash_flow = self._compute_cash_flow(date_from, date_to)
        opening_balance = self._get_opening_cash_balance(date_from)

        lines = []
        seq = [0]

        def add(name, balance, level=0, style=''):
            seq[0] += 1
            lines.append({
                'id': 'cf_%d' % seq[0],
                'name': name,
                'level': level + 1,
                'balance': round(balance, 2),
                'type': style or ('total' if level == 0 else 'detail'),
            })

        # === 一、经营活动 ===
        add('一、经营活动产生的现金流量', 0, level=0, style='section')
        op = cash_flow['operating']
        for name, amounts in op['items'].items():
            net = amounts['in'] - amounts['out']
            if net != 0:
                add(name, net, level=1)
        add('经营活动现金流入小计', op['in'], level=1, style='subtotal')
        for name, amounts in op['items'].items():
            if amounts['out'] > 0:
                add(name, -amounts['out'], level=1)
        add('经营活动现金流出小计', -op['out'], level=1, style='subtotal')
        add('经营活动产生的现金流量净额', op['net'], level=1, style='total')

        # === 二、投资活动 ===
        add('二、投资活动产生的现金流量', 0, level=0, style='section')
        inv = cash_flow['investing']
        for name, amounts in inv['items'].items():
            if amounts['in'] > 0:
                add(name, amounts['in'], level=1)
        add('投资活动现金流入小计', inv['in'], level=1, style='subtotal')
        for name, amounts in inv['items'].items():
            if amounts['out'] > 0:
                add(name, -amounts['out'], level=1)
        add('投资活动现金流出小计', -inv['out'], level=1, style='subtotal')
        add('投资活动产生的现金流量净额', inv['net'], level=1, style='total')

        # === 三、筹资活动 ===
        add('三、筹资活动产生的现金流量', 0, level=0, style='section')
        fin = cash_flow['financing']
        for name, amounts in fin['items'].items():
            if amounts['in'] > 0:
                add(name, amounts['in'], level=1)
        add('筹资活动现金流入小计', fin['in'], level=1, style='subtotal')
        for name, amounts in fin['items'].items():
            if amounts['out'] > 0:
                add(name, -amounts['out'], level=1)
        add('筹资活动现金流出小计', -fin['out'], level=1, style='subtotal')
        add('筹资活动产生的现金流量净额', fin['net'], level=1, style='total')

        # === 四、现金净增加额 ===
        total_net = op['net'] + inv['net'] + fin['net']
        add('四、现金及现金等价物净增加额', total_net, level=0, style='grand_total')
        add('加：期初现金及现金等价物余额', opening_balance, level=1)
        add('五、期末现金及现金等价物余额',
            opening_balance + total_net, level=0, style='grand_total')

        return lines

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get(
                'active_model') or not self.env.context.get('active_id'):
            raise UserError(
                _("Form content is missing, this report cannot be printed."))

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))
        report_lines = self.get_account_lines(data.get('form'))
        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_account_lines': report_lines,
        }
