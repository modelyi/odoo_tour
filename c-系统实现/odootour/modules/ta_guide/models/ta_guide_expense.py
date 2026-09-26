# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaGuideExpense(models.Model):
    """导游报账：提交（导游/移动端口径）→审核→计入单团成本（ta.team.pnl 扩展）。"""
    _name = 'ta.guide.expense'
    _description = '导游报账'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    date = fields.Date(string='报账日期', required=True, default=fields.Date.context_today)
    guide_id = fields.Many2one('res.partner', string='报销导游', required=True,
                               default=lambda self: self.env.user.partner_id, tracking=True)
    departure_id = fields.Many2one('ta.departure', string='团（班期）', required=True,
                                   domain="[('state', 'in', ('confirmed', 'departed', 'settled'))]")
    line_ids = fields.One2many('ta.guide.expense.line', 'expense_id', string='费用明细')
    amount_total = fields.Float(compute='_compute_total', store=True)
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提交'),
        ('approved', '已审核'),
        ('rejected', '已驳回'),
    ], default='draft', required=True, tracking=True, copy=False)
    approved_by = fields.Many2one('res.users', string='审核人', readonly=True, copy=False)
    note = fields.Char()

    @api.depends('line_ids.amount')
    def _compute_total(self):
        for exp in self:
            exp.amount_total = sum(exp.line_ids.mapped('amount'))

    def action_submit(self):
        for exp in self:
            if exp.state not in ('draft', 'rejected'):
                raise UserError("只有草稿或被驳回的报账可以提交。")
            if not exp.line_ids:
                raise UserError("费用明细不能为空。")
            exp.state = 'submitted'

    def action_approve(self):
        for exp in self:
            if exp.state != 'submitted':
                raise UserError("只有已提交的报账可以审核。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("报账审核需要会计权限。")
            if exp.guide_id == self.env.user.partner_id:
                raise AccessError("审核人不能是报销导游本人。")
            exp.approved_by = self.env.user
            exp.state = 'approved'

    def action_reject(self):
        for exp in self:
            if exp.state != 'submitted':
                raise UserError("只有已提交的报账可以驳回。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("报账审核需要会计权限。")
            exp.state = 'rejected'


class TaGuideExpenseLine(models.Model):
    _name = 'ta.guide.expense.line'
    _description = '导游报账明细行'
    _inherit = ['ta.mixin']

    expense_id = fields.Many2one('ta.guide.expense', ondelete='cascade', required=True)
    name = fields.Char(string='事由', required=True)
    amount = fields.Float(string='金额', required=True)
    invoice_ref = fields.Char(string='票据号')

    _amount_positive = models.Constraint(
        'check(amount > 0)', '报账金额必须为正。')
