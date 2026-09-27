# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaRoute(models.Model):
    _name = 'ta.route'
    _description = '线路产品'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'code'

    name = fields.Char(string='线路名称', required=True, tracking=True)
    code = fields.Char(string='编号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.route') or '/')
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', '草稿'),
        ('on_sale', '在售'),
        ('off', '停售'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    stop_ids = fields.One2many('ta.route.stop', 'route_id', string='行程明细')
    price_ids = fields.One2many('ta.route.price', 'route_id', string='价格体系')
    list_price = fields.Float(string='成人门市价', compute='_compute_list_price', store=True)
    days = fields.Integer(string='天数', compute='_compute_days', store=True)
    responsible_id = fields.Many2one('res.users', string='产品负责', default=lambda self: self.env.user)
    description = fields.Html()
    note = fields.Char(string='备注')

    @api.depends('price_ids.kind', 'price_ids.amount', 'price_ids.active')
    def _compute_list_price(self):
        for route in self:
            adult = route.price_ids.filtered(
                lambda p: p.kind == 'adult' and p.active and p.amount > 0)
            route.list_price = min(adult.mapped('amount'), default=0.0)

    @api.depends('stop_ids.day_no')
    def _compute_days(self):
        for route in self:
            route.days = max(route.stop_ids.mapped('day_no'), default=0)

    def action_on_sale(self):
        for route in self:
            if not route.stop_ids:
                raise UserError("在售前必须先录入行程明细。")
            if not route.price_ids.filtered(lambda p: p.kind == 'adult' and p.amount > 0):
                raise UserError("在售前必须至少设置一个成人价。")
            route.state = 'on_sale'

    def action_off(self):
        self.write({'state': 'off'})

    def action_draft(self):
        self.write({'state': 'draft'})

    @api.constrains('state')
    def _check_open_departures(self):
        """停售/回草稿不得遗留未完结发团计划。"""
        for route in self:
            if route.state != 'on_sale':
                blocking = self.env['ta.departure'].search_count([
                    ('route_id', '=', route.id),
                    ('state', 'in', ('open', 'confirmed', 'departed')),
                ])
                if blocking:
                    raise UserError(
                        f"线路「{route.display_name}」仍有 {blocking} 个未完结发团计划，不能离开在售状态。")


class TaRouteStop(models.Model):
    _name = 'ta.route.stop'
    _description = '线路行程站点'
    _order = 'route_id, day_no, sequence'
    _inherit = ['ta.mixin']

    route_id = fields.Many2one('ta.route', string='线路', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    day_no = fields.Integer(string='第几天', required=True, default=1)
    name = fields.Char(string='节点', required=True)
    city = fields.Char(string='城市/地点')
    meal = fields.Char(string='餐食（早/中/晚）')
    accommodation = fields.Char(string='住宿')
    content = fields.Text(string='说明')


class TaRoutePrice(models.Model):
    _name = 'ta.route.price'
    _description = '线路价格'
    _order = 'route_id, kind'
    _inherit = ['ta.mixin']

    route_id = fields.Many2one('ta.route', string='线路', required=True, ondelete='cascade')
    kind = fields.Selection([
        ('adult', '成人'),
        ('child', '儿童'),
        ('child_bed', '儿童含床'),
        ('single', '单房差'),
        ('same_tour', '同团升级差价'),
    ], string='价别', required=True)
    amount = fields.Float(string='金额', required=True, digits=(12, 2))
    currency_id = fields.Many2one(
        'res.currency', string='币种', default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)
    note = fields.Char(string='说明')
