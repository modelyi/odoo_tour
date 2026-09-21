# -*- coding: utf-8 -*-
from odoo import models, fields


class ProjectProject(models.Model):
    """团 1:1 项目：project.project 薄扩展，回链 tour.plan + 共享 analytic。"""
    _inherit = 'project.project'

    tour_plan_id = fields.Many2one('tour.plan', string='团队订单', index=True,
                                   copy=False, ondelete='restrict',
                                   help='1:1 团=项目，计调看板入口（与团共享 analytic）')

    _uniq_tour_plan = models.Constraint('unique(tour_plan_id)', '一个团只能对应一个项目')
