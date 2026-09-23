# -*- coding: utf-8 -*-
"""tour.plan.reg 扩展：订单来源「7 电商」+ 电商销售单回链。"""
from odoo import fields, models


class TourPlanReg(models.Model):
    _inherit = 'tour.plan.reg'

    from_type = fields.Selection(
        selection_add=[('7', '电商')])

    # 电商回链（sale.order 桥接时回填，财务仍以 tour.plan 为唯一口径）
    sale_order_id = fields.Many2one(
        'sale.order', string='电商销售单', index=True, ondelete='set null',
        copy=False, help='来源电商销售单（sale.order，仅回链，不独立出账）')
    sale_order_line_id = fields.Many2one(
        'sale.order.line', string='电商销售单行', index=True, ondelete='set null',
        copy=False, help='来源电商销售单行（sale.order.line）')
