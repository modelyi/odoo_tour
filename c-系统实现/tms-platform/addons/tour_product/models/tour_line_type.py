# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourLineType(models.Model):
    _name = 'tour.line.type'
    _description = '线路分类'
    _order = 'sequence, name'
    _parent_store = True

    name = fields.Char('分类名称', required=True, index=True)
    code = fields.Char('分类编码', index=True)
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)
    description = fields.Text('说明')

    parent_id = fields.Many2one('tour.line.type', string='上级分类', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('tour.line.type', 'parent_id', string='子分类')

    line_ids = fields.One2many('tour.line', 'line_type_id', string='线路产品')
    line_count = fields.Integer('线路数量', compute='_compute_line_count')

    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)
