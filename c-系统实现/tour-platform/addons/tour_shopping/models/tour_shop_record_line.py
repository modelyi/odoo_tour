# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourShopRecordLine(models.Model):
    _name = 'tour.shop.record.line'
    _description = '购物商品明细行'

    record_id = fields.Many2one('tour.shop.record', string='购物记录',
                                required=True, ondelete='cascade')
    item_name = fields.Char('商品名称', required=True)
    quantity = fields.Integer('数量', default=1)
    unit_price = fields.Float('单价', digits=(15, 2))
    amount = fields.Float('金额', digits=(15, 2),
                          compute='_compute_amount', store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.unit_price
