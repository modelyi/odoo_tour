# -*- coding: utf-8 -*-
from odoo import models, fields


class TourBizType(models.Model):
    _name = 'tour.biz.type'
    _description = '业务类型'
    _order = 'sequence, id'

    name = fields.Char('名称', required=True, index=True)
    code = fields.Char('编码', index=True)
    help_code = fields.Char('助记码', index=True)
    brief = fields.Text('摘要')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)

    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
