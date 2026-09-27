# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaGuideCommission(models.Model):
    """导游佣金结算（BS-08）：补贴+规则参数 → 应发（税前）→ 个税 → 税后净额冲抵借款，余额支付。

    AC-18：冲抵口径用税后净额；个税提示写入单据备注与消息。NFR-2：settle 幂等。
    """
    _name = 'ta.guide.commission'
    _description = '导游佣金'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='佣金单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.guide.commission') or '/')
    date = fields.Date(required=True, default=fields.Date.context_today)
    guide_id = fields.Many2one('res.partner', string='导游', required=True, tracking=True)
    departure_id = fields.Many2one('ta.departure', string='发团计划', required=True)
    allowance = fields.Float(string='补贴/出团费', required=True)
    rule_note = fields.Char(string='规则参数', help='如：50元/天×3天+购物零返佣。')
    tax_rate = fields.Float(string='个税税率', default=0.0)
    tax_amount = fields.Float(compute='_compute_amounts', store=True)
    net_amount = fields.Float(compute='_compute_amounts', store=True, tracking=True)
    deducted_total = fields.Float(compute='_compute_amounts', store=True)
    payable_rest = fields.Float(compute='_compute_amounts', store=True)
    deduct_line_ids = fields.One2many('ta.guide.commission.deduct', 'commission_id', string='冲抵借款明细')
    state = fields.Selection([
        ('draft', '草稿'),
        ('settled', '已结算'),
    ], default='draft', required=True, tracking=True, copy=False)
    note = fields.Char()

    @api.depends('allowance', 'tax_rate', 'deduct_line_ids.net_deduct')
    def _compute_amounts(self):
        for c in self:
            c.tax_amount = round(c.allowance * c.tax_rate, 2)
            c.net_amount = c.allowance - c.tax_amount
            c.deducted_total = sum(c.deduct_line_ids.mapped('net_deduct'))
            c.payable_rest = c.net_amount - c.deducted_total

    def action_settle(self):
        """税后净额按最先到期借款优先冲抵；不足部分留余额支付。"""
        for c in self:
            if c.state != 'draft':
                raise UserError("该佣金单已结算，不能重复操作（NFR-2）。")
            if abs((c.tax_amount + c.net_amount) - c.allowance) > 0.01:
                raise UserError("税额与净额不平衡，请检查税率。")
            available = c.net_amount
            loans = self.env['ta.guide.loan'].search([
                ('guide_id', '=', c.guide_id.id),
                ('state', '=', 'paid'),
                ('outstanding', '>', 0.01),
                ('company_id', '=', c.company_id.id),
            ], order='due_date asc, date asc')
            for loan in loans:
                if available <= 0.01:
                    break
                take = min(available, loan.outstanding)
                self.env['ta.guide.commission.deduct'].create({
                    'commission_id': c.id, 'loan_id': loan.id, 'net_deduct': take})
                available = round(available - take, 2)
                if loan.outstanding <= 0.01:
                    loan.state = 'settled'
                    loan.message_post(body=f"借款 {loan.name} 已由佣金单 {c.name} 结清。")
            c.state = 'settled'
            c.message_post(body=(
                f"税后净额 {c.net_amount:.2f} 已冲抵借款 {c.deducted_total:.2f}，"
                f"余额支付 {c.payable_rest:.2f}。个税 {c.tax_amount:.2f} 于下次发团佣金中抵扣。"))
        return True


class TaGuideCommissionDeduct(models.Model):
    _name = 'ta.guide.commission.deduct'
    _description = '佣金冲抵借款行'
    _inherit = ['ta.mixin']

    commission_id = fields.Many2one('ta.guide.commission', ondelete='cascade', required=True)
    loan_id = fields.Many2one('ta.guide.loan', string='借款单', ondelete='restrict', required=True)
    net_deduct = fields.Float(string='冲抵金额（税后净额）', required=True)

    _deduct_positive = models.Constraint(
        'check(net_deduct > 0)', '冲抵金额必须为正。')
