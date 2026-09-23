# -*- coding: utf-8 -*-
from odoo import models, fields


class TourMerge(models.Model):
    _name = 'tour.merge'
    _description = '并团记录'
    _inherit = ['mail.thread']
    _order = 'id desc'

    # 合并目标发团计划
    plan_id = fields.Many2one('tour.plan', string='合并目标发团计划', required=True,
                              index=True, ondelete='cascade',
                              help='并团后报名单 first_plan_id 指向该计划')
    merge_type = fields.Selection([
        ('dsn', '散客并团'),
        ('keyword', '关键字并团'),
        ('fit', '自由行并团'),
    ], string='并团类型', required=True, default='dsn',
       help='散客并团 / 关键字并团 / 自由行并团')
    reg_ids = fields.Many2many('tour.plan.reg', 'tour_merge_tour_plan_reg_rel',
                               'merge_id', 'reg_id', string='并入报名单',
                               help='并入的报名单（保留独立金额）')
    operator_id = fields.Many2one('res.users', string='操作人', required=True,
                                  default=lambda self: self.env.user)
    merge_date = fields.Datetime('并团时间', required=True,
                                 default=lambda self: fields.Datetime.now())
    before_snapshot = fields.Json('并团前快照', help='并团前名单/金额快照（可审计回退）')
    after_snapshot = fields.Json('并团后快照', help='并团后名单/金额快照')
    remark = fields.Text('备注')
