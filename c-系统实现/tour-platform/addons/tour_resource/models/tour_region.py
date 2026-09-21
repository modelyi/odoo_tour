# -*- coding: utf-8 -*-
from odoo import models, fields


class TourRegion(models.Model):
    _name = 'tour.region'
    _description = '区域'
    _order = 'sequence, name'

    name = fields.Char('区域名称', required=True, translate=True)
    code = fields.Char('区域编码', index=True)
    sequence = fields.Integer('排序', default=10)
    parent_id = fields.Many2one('tour.region', string='上级区域', index=True, ondelete='cascade')
    child_ids = fields.One2many('tour.region', 'parent_id', string='下级区域')
    region_type = fields.Selection([
        ('country', '国家'),
        ('province', '省/直辖市'),
        ('city', '市'),
        ('district', '区/县'),
    ], string='区域类型', default='province', required=True)
    active = fields.Boolean('有效', default=True)
    remark = fields.Text('备注')
