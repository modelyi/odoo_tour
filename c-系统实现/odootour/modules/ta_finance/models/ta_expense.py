# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaExpense(models.Model):
    """全员费用报销（BS-15 简化）：提交→审核→生成费用凭证（草稿，付款走 account 原生流程）。

    口径：公司期间费用，不入单团损益（ta.team.pnl）；挂团仅作分析维度。
    审核生成凭证幂等：move_id 已有值不可重复审核。
    """
    _name = 'ta.expense'
    _description = '费用报销'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.expense') or '/')
    reason = fields.Char(string='事由', required=True, tracking=True)
    applicant_id = fields.Many2one('res.users', string='报销人', required=True,
                                   default=lambda self: self.env.user, tracking=True)
    partner_id = fields.Many2one('res.partner', string='收款人', related='applicant_id.partner_id')
    expense_type = fields.Selection([
        ('office', '办公费'),
        ('travel', '差旅费'),
        ('entertainment', '招待费'),
        ('freight', '快递杂费'),
        ('marketing', '营销费'),
        ('other', '其他'),
    ], string='费用类型', required=True, default='office', tracking=True)
    date = fields.Date(string='费用日期', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string='金额', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='币种',
                                  default=lambda self: self.env.company.currency_id)
    departure_id = fields.Many2one('ta.departure', string='关联团（分析用）',
                                   domain="[('state', 'in', ('confirmed', 'departed', 'settled'))]")
    invoice_ref = fields.Char(string='票据号')
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '已提交'),
        ('approved', '已审核'),
        ('rejected', '已驳回'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    approved_by = fields.Many2one('res.users', string='审核人', readonly=True, copy=False)
    move_id = fields.Many2one('account.move', string='生成凭证', readonly=True, copy=False)
    note = fields.Char(string='备注')

    @api.constrains('amount')
    def _check_amount(self):
        for exp in self:
            if exp.amount <= 0:
                raise UserError("报销金额必须为正。")

    def action_submit(self):
        for exp in self:
            if exp.state not in ('draft', 'rejected'):
                raise UserError("只有草稿或被驳回的报销可以提交。")
            if exp.company_id != self.env.company:
                raise AccessError("不允许跨公司操作报销单。")
            exp.state = 'submitted'

    def action_approve(self):
        for exp in self:
            if exp.state != 'submitted':
                raise UserError("只有已提交的报销可以审核。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("报销审核需要会计/财务经理权限。")
            if exp.applicant_id == self.env.user:
                raise AccessError("审核人不能是报销人本人（AC-05 岗位分离）。")
            if exp.move_id:
                raise UserError("该报销单已生成凭证，不能重复审核。")
            exp.move_id = exp._create_move()
            exp.approved_by = self.env.user
            exp.state = 'approved'
        return True

    def action_reject(self):
        for exp in self:
            if exp.state != 'submitted':
                raise UserError("只有已提交的报销可以驳回。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("报销审核需要会计/财务经理权限。")
            exp.state = 'rejected'

    def _create_move(self):
        """借公司费用科目 / 贷员工往来（ICP payable_employee 或收款人应付科目），留草稿待付款。"""
        self.ensure_one()
        expense = self.company_id.expense_account_id
        if not expense:
            raise UserError("公司未设置默认费用科目（会计设置→费用科目），无法落账。")
        partner = self.partner_id
        payable = self.env['account.account'].browse(
            self.env['ir.config_parameter'].sudo().get_int('ta_finance.payable_employee_account_id', 0)
        ).exists() or partner.property_account_payable_id
        if not payable:
            raise UserError("未配置员工往来科目（ta_finance.payable_employee_account_id 或收款人应付科目）。")
        journal = self.env['account.journal'].search(
            [('type', 'in', ('expense', 'purchase')), ('company_id', '=', self.company_id.id)],
            limit=1)
        if not journal:
            raise UserError("当前公司没有费用/采购日记账，无法生成凭证。")
        return self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date,
            'ref': f"费用报销 {self.name} {self.reason}",
            'line_ids': [
                (0, 0, {'name': self.reason, 'partner_id': partner.id,
                        'account_id': expense.id, 'debit': self.amount}),
                (0, 0, {'name': f"应付员工 {partner.name}", 'partner_id': partner.id,
                        'account_id': payable.id, 'credit': self.amount}),
            ],
        })
