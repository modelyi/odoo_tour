# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import UserError


class TourPayChannel(models.Model):
    _name = 'tour.pay.channel'
    _description = '支付渠道'
    _inherit = ['tour.accounting.mixin']
    _order = 'sequence, id'

    name = fields.Char('渠道名称', required=True, index=True)
    channel_type = fields.Selection([
        ('bank_transfer', '银行转账'),
        ('wechat', '微信'),
        ('alipay', '支付宝'),
        ('cash', '现金'),
        ('other', '其他'),
    ], string='渠道类型', required=True, index=True)
    fund_account_code = fields.Char('资金账户编码',
                                    help='1002 银行存款 / 1012 其他货币资金 / 1001 库存现金')
    fund_account_id = fields.Many2one(
        'account.account', string='资金科目', index=True,
        help='收款/付款凭证资金行科目；留空按 fund_account_code / 渠道类型反查')
    fund_account_name = fields.Char('资金账户名称')
    journal_id = fields.Many2one(
        'account.journal', string='日记账',
        help='该渠道收款/付款落账日记账；留空按渠道类型自动路由（bank/general）')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)
    brief = fields.Text('摘要')
    company_id = fields.Many2one('res.company', string='公司',
                                 default=lambda self: self.env.company)

    _uniq_channel_type = models.Constraint(
        'unique(channel_type)',
        '支付渠道类型已存在',
    )

    # 渠道类型 → 资金科目编码映射 [TDS §4.2]
    _FUND_CODE_MAP = {
        'bank_transfer': '1002',
        'wechat': '1012',
        'alipay': '1012',
        'cash': '1001',
        'other': '1012',
    }

    def _get_fund_account(self):
        """返回该渠道的资金科目（account.account）；先取 fund_account_id，
        否则按 fund_account_code / 渠道类型反查 code_store。"""
        self.ensure_one()
        if self.fund_account_id:
            return self.fund_account_id
        code = self.fund_account_code or self._FUND_CODE_MAP.get(self.channel_type)
        if not code:
            raise UserError('支付渠道「%s」未配置资金科目' % self.name)
        account = self.env['account.account'].search([('code', '=', code)], limit=1)
        if not account:
            raise UserError(
                '支付渠道「%s」资金科目编码「%s」未找到，请先安装/配置旅行社科目表'
                % (self.name, code))
        return account

    def _get_receipt_journal(self):
        """返回该渠道收款日记账；银行/微信/支付宝→bank，现金→cash（回退 general）。"""
        self.ensure_one()
        if self.journal_id:
            return self.journal_id
        jtype = 'bank' if self.channel_type in ('bank_transfer', 'wechat', 'alipay') else 'cash'
        journal = self.env['account.journal'].search(
            [('type', '=', jtype),
             ('company_id', 'in', (self.company_id.id, False))], limit=1)
        if not journal:
            journal = self.env['account.journal'].search(
                [('company_id', 'in', (self.company_id.id, False))], limit=1)
        if not journal:
            raise UserError('未找到可用日记账，请先配置')
        return journal
