# -*- coding: utf-8 -*-
from odoo import models, fields


class TourBaseItem(models.Model):
    _name = 'tour.base.item'
    _description = '通用基础数据'
    _order = 'sequence, id'

    name = fields.Char('名称', required=True, index=True)
    item_type = fields.Selection([
        ('room_type', '房型'),
        ('meal_type', '团餐'),
        ('transport', '交通'),
        ('team_type', '团队类型'),
    ], string='类型', required=True, index=True)
    help_code = fields.Char('助记码', index=True)
    brief = fields.Text('摘要')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)

    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
