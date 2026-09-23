# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourBankAccount(models.Model):
    _name = 'tour.bank.account'
    _description = '旅行社银行账户'
    _order = 'sequence, id'

    name = fields.Char('账户名称', required=True, index=True,
                       help='如"海螺散客公户4051"')
    bank_id = fields.Many2one('tour.bank', string='开户行')
    acc_number = fields.Char('银行账号', index=True)
    balance = fields.Float('账户余额', digits=(16, 2))
    taxpayer_no = fields.Char('纳税人识别号')
    trans_fee_rate = fields.Float('转账手续费率%', digits=(5, 2),
                                  help='跨行转账手续费比例')
    active = fields.Boolean('启用', default=True)
    power_area = fields.Char('管辖区域')
    remark = fields.Text('备注')
    sequence = fields.Integer('排序', default=10)
    currency_id = fields.Many2one('res.currency', string='币种',
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='公司',
                                 default=lambda self: self.env.company)

    _uniq_acc_number = models.Constraint(
        'unique(acc_number, company_id)', '同一公司下银行账号不能重复！',
    )

    @api.depends('name', 'acc_number')
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.name or '']
            if rec.acc_number:
                parts.append(rec.acc_number)
            rec.display_name = ' / '.join(parts)
