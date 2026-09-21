# -*- coding: utf-8 -*-
"""办公费用统计报表。

旅行社办公管理 - 办公费用统计报表功能。
"""
from odoo import models, fields, api
from datetime import date
from dateutil.relativedelta import relativedelta


class TourOfficeExpenseReport(models.TransientModel):
    _name = 'tour.office.expense.report'
    _description = '办公费用统计报表'
    
    date_from = fields.Date('开始日期', required=True,
                            default=lambda self: date.today() + relativedelta(day=1))
    date_to = fields.Date('结束日期', required=True,
                          default=lambda self: date.today())
    group_by = fields.Selection([
        ('category', '费用类别'),
        ('employee', '员工'),
        ('month', '月份'),
        ('department', '部门'),
    ], string='分组方式', default='category', required=True)
    
    def action_generate_report(self):
        """生成报表"""
        self.ensure_one()
        
        # 查询办公费用数据
        domain = [
            ('x_guide_id', '=', False),  # 办公费用（无导游）
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', 'in', ['approved', 'posted', 'paid']),
        ]
        
        expenses = self.env['hr.expense'].search(domain)
        
        # 根据分组方式生成报表数据
        report_data = []
        
        if self.group_by == 'category':
            grouped = {}
            for exp in expenses:
                key = exp.product_id.name or '未分类'
                if key not in grouped:
                    grouped[key] = {'count': 0, 'amount': 0}
                grouped[key]['count'] += 1
                grouped[key]['amount'] += exp.total_amount_currency
            
            for category, data in grouped.items():
                report_data.append((0, 0, {
                    'name': category,
                    'count': data['count'],
                    'amount': data['amount'],
                }))
        
        elif self.group_by == 'employee':
            grouped = {}
            for exp in expenses:
                key = exp.employee_id.name or '未知员工'
                if key not in grouped:
                    grouped[key] = {'count': 0, 'amount': 0}
                grouped[key]['count'] += 1
                grouped[key]['amount'] += exp.total_amount_currency
            
            for employee, data in grouped.items():
                report_data.append((0, 0, {
                    'name': employee,
                    'count': data['count'],
                    'amount': data['amount'],
                }))
        
        elif self.group_by == 'month':
            grouped = {}
            for exp in expenses:
                month_key = exp.date.strftime('%Y-%m')
                if month_key not in grouped:
                    grouped[month_key] = {'count': 0, 'amount': 0}
                grouped[month_key]['count'] += 1
                grouped[month_key]['amount'] += exp.total_amount_currency
            
            for month, data in sorted(grouped.items()):
                report_data.append((0, 0, {
                    'name': month,
                    'count': data['count'],
                    'amount': data['amount'],
                }))
        
        elif self.group_by == 'department':
            grouped = {}
            for exp in expenses:
                dept = exp.employee_id.department_id.name if exp.employee_id.department_id else '无部门'
                if dept not in grouped:
                    grouped[dept] = {'count': 0, 'amount': 0}
                grouped[dept]['count'] += 1
                grouped[dept]['amount'] += exp.total_amount_currency
            
            for dept, data in grouped.items():
                report_data.append((0, 0, {
                    'name': dept,
                    'count': data['count'],
                    'amount': data['amount'],
                }))
        
        # 创建报表记录
        report = self.env['tour.office.expense.report.result'].create({
            'date_from': self.date_from,
            'date_to': self.date_to,
            'group_by': self.group_by,
            'line_ids': report_data,
        })
        
        # 返回报表结果视图
        return {
            'name': '办公费用统计报表',
            'type': 'ir.actions.act_window',
            'res_model': 'tour.office.expense.report.result',
            'res_id': report.id,
            'view_mode': 'form',
            'target': 'new',
        }


class TourOfficeExpenseReportResult(models.TransientModel):
    _name = 'tour.office.expense.report.result'
    _description = '办公费用统计报表结果'
    
    date_from = fields.Date('开始日期')
    date_to = fields.Date('结束日期')
    group_by = fields.Selection([
        ('category', '费用类别'),
        ('employee', '员工'),
        ('month', '月份'),
        ('department', '部门'),
    ], string='分组方式')
    line_ids = fields.One2many('tour.office.expense.report.line', 'result_id', string='明细')
    total_count = fields.Integer('总笔数', compute='_compute_total')
    total_amount = fields.Monetary('总金额', currency_field='currency_id', compute='_compute_total')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    
    @api.depends('line_ids.count', 'line_ids.amount')
    def _compute_total(self):
        for result in self:
            result.total_count = sum(result.line_ids.mapped('count'))
            result.total_amount = sum(result.line_ids.mapped('amount'))


class TourOfficeExpenseReportLine(models.TransientModel):
    _name = 'tour.office.expense.report.line'
    _description = '办公费用报表明细'
    
    result_id = fields.Many2one('tour.office.expense.report.result', string='报表', ondelete='cascade')
    name = fields.Char('分组名称')
    count = fields.Integer('笔数')
    amount = fields.Monetary('金额', currency_field='currency_id')
    currency_id = fields.Many2one(related='result_id.currency_id')
