# -*- coding: utf-8 -*-
from odoo import models, fields


class TourPayWay(models.Model):
    _name = 'tour.pay.way'
    _description = '结算方式'
    _order = 'sequence, id'

    name = fields.Char('名称', required=True, index=True)
    code = fields.Char('编码', index=True)
    pay_type = fields.Selection([
        ('cash', '现金'),
        ('transfer', '银行转账'),
        ('credit', '挂账/月结'),
        ('prepaid', '预付'),
    ], string='类型')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)
    brief = fields.Text('摘要')

    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
