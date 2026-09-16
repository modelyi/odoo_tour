# -*- coding: utf-8 -*-
"""导游批量报账向导。

一次录入多条费用（可跨团），批量创建 hr.expense 记录。
"""
from odoo import models, fields, api
from odoo.exceptions import UserError


class BatchExpenseWizard(models.TransientModel):
    _name = 'tour.batch.expense.wizard'
    _description = '导游批量报账向导'

    employee_id = fields.Many2one('hr.employee', string='员工', required=True,
        default=lambda self: self.env.user.employee_id.id or False)
    x_guide_id = fields.Many2one('tour.guide', string='导游',
        help='留空则从员工档案自动关联')
    x_report_type = fields.Selection([
        ('expense', '费用报销'),
        ('income', '收入报账'),
    ], string='报账类型', default='expense', required=True)
    date = fields.Date('费用日期', default=fields.Date.context_today, required=True)

    line_ids = fields.One2many('tour.batch.expense.line', 'wizard_id', string='费用明细')

    def action_create_expenses(self):
        """批量创建 hr.expense 记录"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError('请至少添加一条费用明细')

        guide = self.x_guide_id
        if not guide and self.employee_id:
            guide = self.env['tour.guide'].search(
                [('employee_id', '=', self.employee_id.id)], limit=1)

        expenses = self.env['hr.expense']
        for line in self.line_ids:
            if not line.product_id:
                raise UserError('费用明细第 %d 行未选择费用类别' % line.sequence)
            if line.amount <= 0:
                raise UserError('费用明细第 %d 行金额必须大于 0' % line.sequence)

            expense = self.env['hr.expense'].create({
                'employee_id': self.employee_id.id,
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.amount,
                'total_amount_currency': line.amount * line.quantity,
                'date': self.date,
                'x_report_type': self.x_report_type,
                'x_guide_id': guide.id if guide else False,
                'x_plan_id': line.x_plan_id.id if line.x_plan_id else False,
                'x_loan_id': line.x_loan_id.id if line.x_loan_id else False,
                'x_invoice_no': line.x_invoice_no,
                'payment_mode': 'own_account',
            })
            expenses |= expense

        return {
            'type': 'ir.actions.act_window',
            'name': '已创建费用',
            'res_model': 'hr.expense',
            'view_mode': 'list,form',
            'domain': [('id', 'in', expenses.ids)],
            'target': 'current',
        }


class BatchExpenseLine(models.TransientModel):
    _name = 'tour.batch.expense.line'
    _description = '批量报账明细行'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('tour.batch.expense.wizard', string='向导', ondelete='cascade')
    sequence = fields.Integer('序号', default=10)
    product_id = fields.Many2one('product.product', string='费用类别', required=True,
        domain="[('can_be_expensed', '=', True)]")
    amount = fields.Monetary('金额', currency_field='currency_id', required=True)
    quantity = fields.Integer('数量', default=1)
    currency_id = fields.Many2one(related='wizard_id.employee_id.company_id.currency_id')

    x_plan_id = fields.Many2one('tour.plan', string='团队')
    x_plan_code = fields.Char(related='x_plan_id.plan_code', string='团号')
    x_loan_id = fields.Many2one('tour.guide.loan', string='关联借款',
        domain="[('employee_id', '=', parent.employee_id), ('state', '=', 'disbursed')]")
    x_invoice_no = fields.Char('发票号')
