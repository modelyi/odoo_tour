# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourLineDetail(models.Model):
    _name = 'tour.line.detail'
    _description = '线路行程明细'
    _order = 'sequence, day_no, id'

    line_id = fields.Many2one('tour.line', string='线路产品', required=True,
                              index=True, ondelete='cascade')
    name = fields.Char('行程名称', compute='_compute_name', store=True)
    day_no = fields.Integer('第几天', required=True, default=1)
    title = fields.Char('当天标题')
    city = fields.Char('城市')

    meal_breakfast = fields.Boolean('早餐')
    meal_lunch = fields.Boolean('午餐')
    meal_dinner = fields.Boolean('晚餐')

    hotel = fields.Char('住宿')
    traffic = fields.Char('交通')
    content = fields.Html('行程内容')
    sequence = fields.Integer('排序', default=10)

    @api.depends('day_no', 'title', 'city')
    def _compute_name(self):
        for rec in self:
            if rec.title:
                rec.name = '第%s天 %s' % (rec.day_no, rec.title)
            else:
                rec.name = '第%s天 %s' % (rec.day_no, rec.city or '')
