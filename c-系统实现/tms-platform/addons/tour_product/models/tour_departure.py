# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourDeparture(models.Model):
    _name = 'tour.departure'
    _description = '发团计划'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'

    # === 关联线路 ===
    line_id = fields.Many2one('tour.line', string='线路产品', required=True,
                              index=True, ondelete='cascade', tracking=True)

    # === 计划信息 ===
    name = fields.Char('日期显示', compute='_compute_name', store=True)
    start_date = fields.Date('出发日期', required=True, index=True, tracking=True)
    end_date = fields.Date('返程日期', tracking=True)

    # === 位次 ===
    seats = fields.Integer('总位数', default=0)
    booked_seats = fields.Integer('已订位数', default=0)
    remain_seats = fields.Integer('余位', compute='_compute_remain_seats', store=True)

    # === 价格 ===
    price_adult = fields.Float('成人价', digits='Product Price')
    price_child = fields.Float('儿童价', digits='Product Price')

    # === 状态 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('published', '已发布'),
        ('ended', '已结束'),
    ], string='状态', default='draft', tracking=True, index=True)
    active = fields.Boolean('启用', default=True, tracking=True)

    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)

    @api.depends('line_id', 'start_date')
    def _compute_name(self):
        for rec in self:
            if rec.line_id and rec.start_date:
                rec.name = '%s %s' % (rec.line_id.name, rec.start_date)
            elif rec.start_date:
                rec.name = str(rec.start_date)
            else:
                rec.name = rec.line_id.name or ''

    @api.depends('seats', 'booked_seats')
    def _compute_remain_seats(self):
        for rec in self:
            rec.remain_seats = rec.seats - rec.booked_seats

    # === 动作 ===
    def action_publish(self):
        self.write({'state': 'published'})

    def action_end(self):
        self.write({'state': 'ended'})

    def action_draft(self):
        self.write({'state': 'draft'})
