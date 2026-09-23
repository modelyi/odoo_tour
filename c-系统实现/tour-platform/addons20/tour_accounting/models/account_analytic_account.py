# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    tour_plan_id = fields.Many2one(
        'tour.plan', string='团队订单', index=True, ondelete='restrict',
        help='一团一核算：反向关联 tour.plan（1:1）')

    _uniq_tour_plan = models.Constraint(
        'unique(tour_plan_id)',
        '该团队订单已存在分析账户（一团一核算）',
    )
