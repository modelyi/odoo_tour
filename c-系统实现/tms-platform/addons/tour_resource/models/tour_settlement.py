# -*- coding: utf-8 -*-
from odoo import models, fields


class TourSettlementMethod(models.Model):
    _name = 'tour.settlement.method'
    _description = '结算方式'
    _order = 'sequence, name'

    name = fields.Char('结算方式', required=True, translate=True)
    code = fields.Char('编码', index=True)
    sequence = fields.Integer('排序', default=10)
    settlement_type = fields.Selection([
        ('cash', '现付'),
        ('prepaid', '预付'),
        ('monthly', '月结'),
        ('signed', '签单'),
        ('other', '其他'),
    ], string='结算类型', default='cash', required=True)
    days_due = fields.Integer('账期天数', default=0, help='月结/签单方式的付款期限')
    active = fields.Boolean('有效', default=True)
    remark = fields.Text('备注')
