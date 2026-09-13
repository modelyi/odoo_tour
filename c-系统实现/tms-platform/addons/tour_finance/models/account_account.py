# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountAccount(models.Model):
    _inherit = 'account.account'

    tour_vat_deductible = fields.Boolean(
        '差额征税可扣除', default=False,
        help='[财税2016-36号] 旅游服务差额征税：住宿/餐饮/交通/门票/地接/签证费可扣除；'
             '导服/保险/自费/购物不可扣除')
