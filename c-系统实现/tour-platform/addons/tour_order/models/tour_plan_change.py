# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourPlanChange(models.Model):
    _name = 'tour.plan.change'
    _description = '单团变更记录'
    _inherit = ['mail.thread']
    _order = 'id desc'

    # 注：create_uid（创建人）/ create_date（创建时间）为 Odoo ORM 自动字段，
    # 对应规格 BS-02 §8.5 的创建人/创建时间，无需重复定义。

    plan_id = fields.Many2one('tour.plan', string='变更后团队订单', required=True,
                              index=True, ondelete='cascade',
                              help='变更团（PlanType=7，团号 [变更-N]）')
    origin_plan_id = fields.Many2one('tour.plan', string='原团队订单', required=True,
                                     index=True, ondelete='restrict',
                                     help='原团队订单（变更团 first_plan_id 指向它溯源）')
    change_type = fields.Selection([
        ('add_guest', '增人'),
        ('remove_guest', '减人'),
        ('change_room', '改房型'),
        ('change_route', '改行程'),
    ], string='变更类型')
    change_reason = fields.Text('变更原因')
    old_value = fields.Json('变更前值')
    new_value = fields.Json('变更后值')
    price_diff = fields.Float('价差', digits=(16, 2))
    audit_chk = fields.Boolean('审核状态')

    @api.constrains('plan_id', 'origin_plan_id')
    def _check_not_same(self):
        for rec in self:
            if rec.plan_id and rec.origin_plan_id and rec.plan_id == rec.origin_plan_id:
                raise ValidationError('变更后团队订单不能与原团队订单相同')

    @api.model_create_multi
    def create(self, vals_list):
        """变更约束：已出团/已归档的订单不可变更（BS-02 §7.7 规则 5）"""
        for vals in vals_list:
            origin = self.env['tour.plan'].browse(vals.get('origin_plan_id'))
            if origin and origin.state in ('in_progress', 'completed', 'archived'):
                raise ValidationError('已出团/已归档的订单不可变更')
        return super().create(vals_list)
