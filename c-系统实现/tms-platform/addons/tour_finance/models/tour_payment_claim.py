# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourPaymentClaim(models.Model):
    _name = 'tour.payment.claim'
    _description = '收款登记/认领'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'pay_date desc, id desc'

    # === 标识 ===
    name = fields.Char('收款编号', required=True, copy=False, default='新建',
                       help='自动流水，如 SK-000123')
    payee_id = fields.Many2one('res.users', string='收款人',
                               default=lambda self: self.env.user,
                               help='收款人（自动=当前用户）')

    # === 收款信息 ===
    supplier_id = fields.Many2one('res.partner', string='付款方(客户)', index=True,
                                  help='允许为空（待认领：55% 收款未关联客户）')
    pay_date = fields.Date('收款日期', default=fields.Date.context_today, required=True)
    pay_money = fields.Float('收款金额', digits=(16, 2), required=True)
    use_money = fields.Float('已使用金额', digits=(16, 2), default=0.0)
    balance_money = fields.Float('余额', digits=(16, 2), compute='_compute_balance_money',
                                 store=True, help='= pay_money - use_money，强制 compute 不可手工改')

    # === 账户与认领 ===
    account_id = fields.Many2one('tour.bank.account', string='收款账户', index=True,
                                 help='允许为「未指定/待匹配」')
    plan_id = fields.Many2one('tour.plan', string='认领到团', index=True,
                              help='收款认领关联团队；待认领时为空')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)

    # === 结算方式两维度 ===
    pay_way_id = fields.Many2one('tour.pay.way', string='收付场景', index=True,
                                 help='签单/导游现付/公司现收等 7 种（复用 tour.pay.way）')
    pay_channel_id = fields.Many2one('tour.pay.channel', string='支付渠道', index=True,
                                     help='银行转账/微信/支付宝/现金/其他')

    # === 付款方信息 ===
    bank_name_pay = fields.Char('付款方银行')
    account_name_pay = fields.Char('付款方户名')
    account_no_pay = fields.Char('付款方账号')
    tax_code = fields.Char('税号')

    # === 手续费 ===
    trans_fee_rate = fields.Float('手续费率(%)', digits=(5, 2))
    trans_fee = fields.Float('手续费', digits=(16, 2), compute='_compute_trans_fee',
                             store=True, help='= pay_money × trans_fee_rate')

    brief = fields.Text('摘要')
    star_state = fields.Boolean('星标')

    # === 认领状态机（0待认领/1待审核/2已审核/3已平账） ===
    claim_state = fields.Selection([
        ('0', '待认领'),
        ('1', '待审核'),
        ('2', '已审核'),
        ('3', '已平账'),
    ], string='认领状态', default='0', required=True, index=True)

    # === 归属/留痕 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')
    op_user_id = fields.Many2one('res.users', string='操作员',
                                 default=lambda self: self.env.user)
    op_date = fields.Datetime('操作时间', default=fields.Datetime.now)

    _uniq_claim_name = models.Constraint(
        'unique(name)',
        '收款编号已存在',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.payment.claim') or '新建'
        return super().create(vals_list)

    @api.depends('pay_money', 'use_money')
    def _compute_balance_money(self):
        for rec in self:
            rec.balance_money = (rec.pay_money or 0.0) - (rec.use_money or 0.0)

    @api.depends('pay_money', 'trans_fee_rate')
    def _compute_trans_fee(self):
        for rec in self:
            rec.trans_fee = (rec.pay_money or 0.0) * (rec.trans_fee_rate or 0.0) / 100.0

    @api.constrains('pay_money')
    def _check_pay_money(self):
        for rec in self:
            if rec.pay_money <= 0:
                raise ValidationError('收款金额必须大于 0')

    @api.constrains('pay_way_id', 'pay_channel_id', 'account_id')
    def _check_channel_account(self):
        """签单（挂账/月结）不产生即时收付，跳过资金账户校验；
        电子渠道（银行转账/微信/支付宝）必须选择收款账户。"""
        for rec in self:
            if rec.pay_way_id and rec.pay_way_id.pay_type == 'credit':
                continue
            if (rec.pay_channel_id
                    and rec.pay_channel_id.channel_type in ('bank_transfer', 'wechat', 'alipay')
                    and not rec.account_id):
                raise ValidationError('银行转账/微信/支付宝渠道必须选择收款账户')

    # === 状态机 ===
    def action_claim(self):
        """业务员认领：待认领 → 待审核，须关联团队"""
        for rec in self:
            if rec.claim_state != '0':
                raise ValidationError('仅「待认领」收款可认领')
            if not rec.plan_id:
                raise ValidationError('认领必须关联团队（plan_id）')
            rec.claim_state = '1'

    def action_audit(self):
        """会计审核：待审核 → 已审核"""
        for rec in self:
            if rec.claim_state != '1':
                raise ValidationError('仅「待审核」收款可审核')
            rec.claim_state = '2'

    def action_settle(self):
        """平账：已审核 → 已平账"""
        for rec in self:
            if rec.claim_state != '2':
                raise ValidationError('仅「已审核」收款可平账')
            rec.claim_state = '3'

    def action_reject(self):
        """退回：待审核 → 待认领"""
        for rec in self:
            if rec.claim_state != '1':
                raise ValidationError('仅「待审核」收款可退回')
            rec.claim_state = '0'
