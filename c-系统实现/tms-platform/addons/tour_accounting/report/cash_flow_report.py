# -*- coding: utf-8 -*-
#############################################################################
#
#    TMS Cash Flow Report - Direct Method Implementation
#    基于会计分录的现金流量分析（直接法）
#
#############################################################################
import re
import time
from odoo import api, models, _
from odoo.exceptions import UserError


class ReportCashFlow(models.AbstractModel):
    _name = 'report.tour_accounting.report_cash_flow'
    _description = 'Cash Flow Report (Direct Method)'

    # 现金及现金等价物账户类型
    CASH_ACCOUNT_TYPES = ['asset_cash', 'asset_current']

    def _get_cash_accounts(self):
        """获取所有现金及现金等价物账户"""
        return self.env['account.account'].search([
            ('account_type', 'in', self.CASH_ACCOUNT_TYPES),
        ])

    def _classify_cash_flow(self, cash_line, counterpart_line):
        """
        根据对方科目分类现金流量
        
        Args:
            cash_line: 现金账户的分录行
            counterpart_line: 对方科目的分录行
        
        Returns:
            dict: {'category': 'operating/investing/financing', 'direction': 'in/out', 'amount': float}
        """
        cash_amount = cash_line.debit - cash_line.credit  # 正数=流入，负数=流出
        if cash_amount == 0:
            return None

        counterpart_type = counterpart_line.account_id.account_type
        
        # 经营活动 - 收入类（现金流入）
        if counterpart_type in ['income', 'income_other']:
            return {
                'category': 'operating',
                'direction': 'in',
                'amount': abs(cash_amount),
                'description': '销售商品、提供劳务收到的现金',
            }
        
        # 经营活动 - 成本费用类（现金流出）
        if counterpart_type in ['expense', 'expense_direct_cost', 'expense_depreciation']:
            return {
                'category': 'operating',
                'direction': 'out',
                'amount': abs(cash_amount),
                'description': '购买商品、接受劳务支付的现金',
            }
        
        # 经营活动 - 应收应付（营运资金变动）
        if counterpart_type == 'asset_receivable':
            if cash_amount > 0:  # 应收账款减少 = 现金流入
                return {
                    'category': 'operating',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                    'description': '收到客户款项',
                }
            else:  # 应收账款增加 = 现金流出（赊销）
                return None  # 不涉及现金
        
        if counterpart_type == 'liability_payable':
            if cash_amount < 0:  # 应付账款减少 = 现金流出
                return {
                    'category': 'operating',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                    'description': '支付供应商款项',
                }
            else:  # 应付账款增加 = 现金流入（赊购）
                return None  # 不涉及现金
        
        # 投资活动
        if counterpart_type in ['asset_fixed', 'asset_non_current']:
            if cash_amount < 0:  # 购买固定资产 = 现金流出
                return {
                    'category': 'investing',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                    'description': '购建固定资产支付的现金',
                }
            else:  # 处置固定资产 = 现金流入
                return {
                    'category': 'investing',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                    'description': '处置固定资产收到的现金',
                }
        
        # 筹资活动
        if counterpart_type == 'equity':
            if cash_amount > 0:  # 吸收投资 = 现金流入
                return {
                    'category': 'financing',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                    'description': '吸收投资收到的现金',
                }
            else:  # 分配股利 = 现金流出
                return {
                    'category': 'financing',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                    'description': '分配股利、利润支付的现金',
                }
        
        if counterpart_type == 'liability_non_current':
            if cash_amount > 0:  # 取得借款 = 现金流入
                return {
                    'category': 'financing',
                    'direction': 'in',
                    'amount': abs(cash_amount),
                    'description': '取得借款收到的现金',
                }
            else:  # 偿还借款 = 现金流出
                return {
                    'category': 'financing',
                    'direction': 'out',
                    'amount': abs(cash_amount),
                    'description': '偿还债务支付的现金',
                }
        
        # 未分类（可能是现金内部转账）
        return None

    def _compute_cash_flow(self, date_from, date_to):
        """
        计算期间内的现金流量
        
        Returns:
            dict: {
                'operating': {'in': float, 'out': float, 'net': float, 'items': []},
                'investing': {'in': float, 'out': float, 'net': float, 'items': []},
                'financing': {'in': float, 'out': float, 'net': float, 'items': []},
            }
        """
        cash_accounts = self._get_cash_accounts()
        if not cash_accounts:
            return {
                'operating': {'in': 0, 'out': 0, 'net': 0, 'items': []},
                'investing': {'in': 0, 'out': 0, 'net': 0, 'items': []},
                'financing': {'in': 0, 'out': 0, 'net': 0, 'items': []},
            }

        # 查询期间内所有涉及现金的分录行
        move_lines = self.env['account.move.line'].search([
            ('account_id', 'in', cash_accounts.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ])

        result = {
            'operating': {'in': 0, 'out': 0, 'net': 0, 'items': []},
            'investing': {'in': 0, 'out': 0, 'net': 0, 'items': []},
            'financing': {'in': 0, 'out': 0, 'net': 0, 'items': []},
        }

        for line in move_lines:
            # 找到同一分录中的对方科目（排除现金账户本身）
            counterpart_lines = line.move_id.line_ids.filtered(
                lambda l: l.account_id not in cash_accounts
            )

            for counterpart in counterpart_lines:
                classification = self._classify_cash_flow(line, counterpart)
                if classification:
                    category = classification['category']
                    direction = classification['direction']
                    amount = classification['amount']

                    result[category][direction] += amount
                    
                    # 记录明细
                    result[category]['items'].append({
                        'date': line.move_id.date,
                        'move_name': line.move_id.name,
                        'description': classification['description'],
                        'counterpart_account': counterpart.account_id.name,
                        'amount': amount if direction == 'in' else -amount,
                        'move_id': line.move_id.id,
                    })

        # 计算净额
        for category in ['operating', 'investing', 'financing']:
            result[category]['net'] = (
                result[category]['in'] - result[category]['out']
            )

        return result

    def get_account_lines(self, data):
        """生成现金流量表行数据"""
        account_report = self.env['account.financial.report'].search(
            [('id', '=', data['account_report_id'][0])])
        
        # 获取期间
        context = data.get('used_context', {})
        date_from = context.get('date_from')
        date_to = context.get('date_to')
        
        if not date_from or not date_to:
            return []

        # 计算现金流量
        cash_flow = self._compute_cash_flow(date_from, date_to)
        
        # 构建报表行
        lines = []
        
        # 一、经营活动
        lines.append({
            'id': 'operating',
            'name': '一、经营活动产生的现金流量',
            'level': 0,
            'balance': cash_flow['operating']['net'],
            'type': 'section',
        })
        
        lines.append({
            'id': 'operating_in',
            'name': '经营活动现金流入',
            'level': 1,
            'balance': cash_flow['operating']['in'],
            'type': 'subtotal',
            'parent': 'operating',
        })
        
        # 经营活动明细
        for item in cash_flow['operating']['items']:
            if item['amount'] > 0:
                lines.append({
                    'id': f"op_in_{item['move_id']}",
                    'name': f"{item['date']} {item['move_name']} - {item['description']}",
                    'level': 2,
                    'balance': item['amount'],
                    'type': 'detail',
                    'parent': 'operating_in',
                    'move_id': item['move_id'],
                })
        
        lines.append({
            'id': 'operating_out',
            'name': '经营活动现金流出',
            'level': 1,
            'balance': -cash_flow['operating']['out'],
            'type': 'subtotal',
            'parent': 'operating',
        })
        
        # 经营活动流出明细
        for item in cash_flow['operating']['items']:
            if item['amount'] < 0:
                lines.append({
                    'id': f"op_out_{item['move_id']}",
                    'name': f"{item['date']} {item['move_name']} - {item['description']}",
                    'level': 2,
                    'balance': item['amount'],
                    'type': 'detail',
                    'parent': 'operating_out',
                    'move_id': item['move_id'],
                })
        
        lines.append({
            'id': 'operating_net',
            'name': '经营活动产生的现金流量净额',
            'level': 1,
            'balance': cash_flow['operating']['net'],
            'type': 'total',
            'parent': 'operating',
        })
        
        # 二、投资活动
        lines.append({
            'id': 'investing',
            'name': '二、投资活动产生的现金流量',
            'level': 0,
            'balance': cash_flow['investing']['net'],
            'type': 'section',
        })
        
        lines.append({
            'id': 'investing_in',
            'name': '投资活动现金流入',
            'level': 1,
            'balance': cash_flow['investing']['in'],
            'type': 'subtotal',
            'parent': 'investing',
        })
        
        for item in cash_flow['investing']['items']:
            if item['amount'] > 0:
                lines.append({
                    'id': f"inv_in_{item['move_id']}",
                    'name': f"{item['date']} {item['move_name']} - {item['description']}",
                    'level': 2,
                    'balance': item['amount'],
                    'type': 'detail',
                    'parent': 'investing_in',
                    'move_id': item['move_id'],
                })
        
        lines.append({
            'id': 'investing_out',
            'name': '投资活动现金流出',
            'level': 1,
            'balance': -cash_flow['investing']['out'],
            'type': 'subtotal',
            'parent': 'investing',
        })
        
        for item in cash_flow['investing']['items']:
            if item['amount'] < 0:
                lines.append({
                    'id': f"inv_out_{item['move_id']}",
                    'name': f"{item['date']} {item['move_name']} - {item['description']}",
                    'level': 2,
                    'balance': item['amount'],
                    'type': 'detail',
                    'parent': 'investing_out',
                    'move_id': item['move_id'],
                })
        
        lines.append({
            'id': 'investing_net',
            'name': '投资活动产生的现金流量净额',
            'level': 1,
            'balance': cash_flow['investing']['net'],
            'type': 'total',
            'parent': 'investing',
        })
        
        # 三、筹资活动
        lines.append({
            'id': 'financing',
            'name': '三、筹资活动产生的现金流量',
            'level': 0,
            'balance': cash_flow['financing']['net'],
            'type': 'section',
        })
        
        lines.append({
            'id': 'financing_in',
            'name': '筹资活动现金流入',
            'level': 1,
            'balance': cash_flow['financing']['in'],
            'type': 'subtotal',
            'parent': 'financing',
        })
        
        for item in cash_flow['financing']['items']:
            if item['amount'] > 0:
                lines.append({
                    'id': f"fin_in_{item['move_id']}",
                    'name': f"{item['date']} {item['move_name']} - {item['description']}",
                    'level': 2,
                    'balance': item['amount'],
                    'type': 'detail',
                    'parent': 'financing_in',
                    'move_id': item['move_id'],
                })
        
        lines.append({
            'id': 'financing_out',
            'name': '筹资活动现金流出',
            'level': 1,
            'balance': -cash_flow['financing']['out'],
            'type': 'subtotal',
            'parent': 'financing',
        })
        
        for item in cash_flow['financing']['items']:
            if item['amount'] < 0:
                lines.append({
                    'id': f"fin_out_{item['move_id']}",
                    'name': f"{item['date']} {item['move_name']} - {item['description']}",
                    'level': 2,
                    'balance': item['amount'],
                    'type': 'detail',
                    'parent': 'financing_out',
                    'move_id': item['move_id'],
                })
        
        lines.append({
            'id': 'financing_net',
            'name': '筹资活动产生的现金流量净额',
            'level': 1,
            'balance': cash_flow['financing']['net'],
            'type': 'total',
            'parent': 'financing',
        })
        
        # 四、现金净增加额
        total_net = (
            cash_flow['operating']['net'] +
            cash_flow['investing']['net'] +
            cash_flow['financing']['net']
        )
        
        lines.append({
            'id': 'total_net',
            'name': '四、现金及现金等价物净增加额',
            'level': 0,
            'balance': total_net,
            'type': 'grand_total',
        })
        
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
