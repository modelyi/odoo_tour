# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TourPlan(models.Model):
    _inherit = 'tour.plan'

    shop_record_ids = fields.One2many(
        'tour.shop.record', 'plan_id', string='购物记录')
    shop_record_count = fields.Integer('购物次数', compute='_compute_shop_stats')
    shop_total_amount = fields.Float(
        '购物总金额', digits=(15, 2), compute='_compute_shop_stats')
    shop_commission_amount = fields.Float(
        '返佣总金额', digits=(16, 2), compute='_compute_shop_stats')

    @api.depends('shop_record_ids', 'shop_record_ids.total_amount',
                 'shop_record_ids.commission_amount', 'shop_record_ids.state')
    def _compute_shop_stats(self):
        for plan in self:
            records = plan.shop_record_ids.filtered(
                lambda r: r.state != 'cancelled')
            plan.shop_record_count = len(records)
            plan.shop_total_amount = sum(records.mapped('total_amount'))
            plan.shop_commission_amount = sum(records.mapped('commission_amount'))

    def action_view_shopping(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '购物记录',
            'res_model': 'tour.shop.record',
            'view_mode': 'list,pivot,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
            'search_view_id': self.env.ref(
                'tour_shopping.view_tour_shop_record_single_search').id,
        }
