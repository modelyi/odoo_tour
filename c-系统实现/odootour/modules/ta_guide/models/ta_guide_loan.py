# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaGuideLoan(models.Model):
    """导游借款：申请→审批→发放（挂公司配置的借款科目，1221 口径）→佣金冲抵。

    逾期提醒：due_date 已过且未结清，列表/日历红色标记（cron 双跑防护不适用，纯计算字段）。
    """
    _name = 'ta.guide.loan'
    _description = '导游借款'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='借款单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.guide.loan') or '/')
    guide_id = fields.Many2one('res.partner', string='导游', required=True, tracking=True)
    departure_id = fields.Many2one('ta.departure', string='关联班期')
    date = fields.Date(string='申请日期', required=True, default=fields.Date.context_today)
    amount = fields.Float(string='借款金额', required=True)
    due_date = fields.Date(string='应结清日')
    date_paid = fields.Date(string='发放日', readonly=True, copy=False)
    paid_move_id = fields.Many2one('account.move', string='发放凭证', readonly=True, copy=False)
    journal_id = fields.Many2one('account.journal', string='付款账户',
                                 domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    deducted_amount = fields.Float(string='已冲抵', compute='_compute_balance', store=True)
    outstanding = fields.Float(string='未结清', compute='_compute_balance', store=True)
    is_overdue = fields.Boolean(compute='_compute_overdue')
    state = fields.Selection([
        ('draft', '草稿'),
        ('approved', '已审批'),
        ('paid', '已发放'),
        ('settled', '已结清'),
        ('cancel', '已取消'),
    ], default='draft', required=True, tracking=True, copy=False)
    note = fields.Char()

    _amount_positive = models.Constraint(
        'check(amount > 0)', '借款金额必须为正（NFR-1：金额方向不取绝对值）。')

    @api.depends('deduct_line_ids.net_deduct')
    def _compute_balance(self):
        for loan in self:
            loan.deducted_amount = sum(loan.deduct_line_ids.mapped('net_deduct'))
            loan.outstanding = loan.amount - loan.deducted_amount

    @api.depends('due_date', 'state', 'outstanding')
    def _compute_overdue(self):
        today = fields.Date.context_today(self)
        for loan in self:
            loan.is_overdue = bool(loan.due_date and loan.due_date < today
                                   and loan.state not in ('settled', 'cancel'))

    deduct_line_ids = fields.One2many('ta.guide.commission.deduct', 'loan_id', string='冲抵明细')

    def action_approve(self):
        for loan in self:
            if loan.state != 'draft':
                raise UserError("只有草稿借款可以申请核批。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("借款审批需要会计权限。")
            if loan.guide_id == self.env.user.partner_id:
                raise AccessError("审批人不能是借款导游本人。")
            loan.state = 'approved'

    def action_pay(self):
        for loan in self:
            if loan.state != 'approved':
                raise UserError("只有已审批借款可以发放。")
            if not loan.journal_id:
                raise UserError("请先选择付款账户。")
            icp = self.env['ir.config_parameter'].sudo()
            acc_id = icp.get_int('ta_guide.loan_account_id', 0)
            loan_account = self.env['account.account'].browse(acc_id).exists()
            if not loan_account:
                raise UserError("未配置导游借款科目（公司 1221 其他应收款-导游借款），无法发放。")
            if not loan.journal_id.default_account_id:
                raise UserError(f"日记账「{loan.journal_id.name}」未设置默认科目。")
            move = self.env['account.move'].create({
                'journal_id': loan.journal_id.id,
                'date': fields.Date.context_today(loan),
                'ref': f"导游借款 {loan.name} / {loan.guide_id.name}",
                'line_ids': [
                    (0, 0, {'name': loan.name, 'partner_id': loan.guide_id.id,
                            'account_id': loan_account.id, 'debit': loan.amount}),
                    (0, 0, {'name': loan.name,
                            'account_id': loan.journal_id.default_account_id.id,
                            'credit': loan.amount}),
                ],
            })
            move.action_post()
            loan.paid_move_id = move
            loan.date_paid = move.date
            loan.state = 'paid'
        return True

    def action_cancel(self):
        for loan in self:
            if loan.state not in ('draft', 'approved'):
                raise UserError("已发放的借款不能取消，请走佣金冲抵或还款。")
            loan.state = 'cancel'
