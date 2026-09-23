# -*- coding: utf-8 -*-
"""product.product 旅行社扩展：导游费用类别类型映射。"""
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    x_expense_type = fields.Selection([
        ('vehicle', '车费'),
        ('meal', '餐费'),
        ('ticket', '门票费'),
        ('hotel', '房费'),
        ('visa', '签证费'),
        ('guide', '导服费'),
        ('other', '其他'),
    ], string='导游费用类型',
       help='导游报账时按此字段判断差额征税可扣除性质（车/餐/门票/房/签证可扣除）')
