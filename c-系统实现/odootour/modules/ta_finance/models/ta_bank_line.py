# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TaBankLine(models.Model):
    """收款登记（三步闭环第 1 步，出纳录入银行到账）。"""
    _name = 'ta.bank.line'
    _description = '收款登记（银行到账）'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    date = fields.Date(string='到账日期', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string='到账金额', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id, required=True)
    journal_id = fields.Many2one(
        'account.journal', string='收款账户（日记账）', required=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]")
    partner_name = fields.Char(string='付款方名称', help='银行流水上的对方户名。')
    partner_id = fields.Many2one('res.partner', string='付款方')
    ref = fields.Char(string='流水号/摘要')
    note = fields.Char()
    registered_by = fields.Many2one(
        'res.users', string='登记人', readonly=True, required=True,
        default=lambda self: self.env.user)
    claimed_amount = fields.Monetary(
        string='已认领金额', compute='_compute_claimed', store=True,
        currency_field='currency_id')
    residual = fields.Monetary(compute='_compute_claimed', store=True, currency_field='currency_id')
    state = fields.Selection([
        ('to_claim', '待认领'),
        ('partial', '部分认领'),
        ('claimed', '已认领'),
    ], compute='_compute_claimed', store=True)
    claim_line_ids = fields.One2many('ta.claim.line', 'bank_line_id', string='认领明细')

    @api.depends('claim_line_ids.claim_id.state', 'claim_line_ids.amount')
    def _compute_claimed(self):
        for line in self:
            done = sum(line.claim_line_ids.filtered(
                lambda l: l.claim_id.state == 'approved').mapped('amount'))
            line.claimed_amount = done
            line.residual = line.amount - done
            if not done:
                line.state = 'to_claim'
            elif done + 0.01 >= line.amount:
                line.state = 'claimed'
            else:
                line.state = 'partial'

    def amount_reserved(self):
        """submitted 未审核认领单占用的金额。"""
        self.ensure_one()
        return sum(self.claim_line_ids.filtered(
            lambda l: l.claim_id.state == 'submitted').mapped('amount'))
