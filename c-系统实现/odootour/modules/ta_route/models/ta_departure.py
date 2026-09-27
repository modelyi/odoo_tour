# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaDeparture(models.Model):
    _name = 'ta.departure'
    _description = '发团计划（发团计划）'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date_start desc, code'

    name = fields.Char(compute='_compute_name', store=True)
    code = fields.Char(string='计划号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.departure') or '/')
    route_id = fields.Many2one(
        'ta.route', string='线路', required=True, ondelete='restrict', index=True,
        domain="[('state', '=', 'on_sale')]")
    biz_mode_id = fields.Many2one('ta.biz.mode', string='业务模式',
                                  domain="[('is_alias', '=', False)]")
    date_start = fields.Date(string='出发日', required=True, tracking=True)
    date_end = fields.Date(string='返回日')
    seats_total = fields.Integer(string='名额', required=True, default=0)
    seats_min = fields.Integer(string='成团线', default=0,
                               help='低于该人数确认成团需要管理层权限。')
    seats_used = fields.Integer(string='已占位', readonly=True, copy=False, default=0,
                                help='由报名单占用/释放维护，禁止手改。')
    seats_free = fields.Integer(compute='_compute_seats_free')
    guide_ids = fields.Many2many('res.users', string='导游/领队')
    state = fields.Selection([
        ('planning', '计划'),
        ('open', '报名中'),
        ('confirmed', '确认成团'),
        ('departed', '已发团'),
        ('settled', '结算完成'),
        ('merged', '已并团'),
        ('cancel', '取消'),
    ], string='状态', default='planning', required=True, tracking=True, copy=False)
    merge_target_id = fields.Many2one('ta.departure', string='并团目标', readonly=True, copy=False)
    note = fields.Char()

    @api.depends('route_id.name', 'code')
    def _compute_name(self):
        for dep in self:
            dep.name = f"{dep.route_id.name or ''} {dep.code or ''}".strip()

    @api.depends('seats_total', 'seats_used')
    def _compute_seats_free(self):
        for dep in self:
            dep.seats_free = dep.seats_total - dep.seats_used

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for dep in self:
            if dep.date_end and dep.date_end < dep.date_start:
                raise UserError("返回日不能早于出发日。")

    @api.constrains('seats_total', 'seats_min')
    def _check_seats(self):
        for dep in self:
            if dep.seats_total <= 0:
                raise UserError("名额必须大于 0。")
            if dep.seats_min > dep.seats_total:
                raise UserError("成团线不能高于名额。")

    # ---- 占位 API（ta_order 在 M2 接入；NFR-2：调用方保证幂等）----
    def change_seats(self, delta):
        self.ensure_one()
        if self.state not in ('open', 'confirmed'):
            raise UserError(f"发团计划「{self.display_name}」当前不允许占位/释放（状态：{self.state}）。")
        new_used = self.seats_used + delta
        if new_used < 0:
            raise UserError("释放数量超过已占位。")
        if new_used > self.seats_total:
            raise UserError(f"超出发团计划余位（余 {self.seats_free}）。")
        self.seats_used = new_used
        return new_used

    # ---- 状态机 ----
    def action_open(self):
        for dep in self:
            if dep.route_id.state != 'on_sale':
                raise UserError("线路不在售，发团计划不能开放报名。")
            if dep.state != 'planning':
                raise UserError("只有计划状态的发团计划可以开放报名。")
            dep.state = 'open'

    def action_confirm(self):
        """确认成团：不足成团线仅管理层可强行确认（源头留痕由 chatter 记录）。"""
        can_force = self.env.user.has_group('ta_base.group_ta_manager')
        for dep in self:
            if dep.state != 'open':
                raise UserError("只有报名中的发团计划可以确认成团。")
            if dep.seats_used < dep.seats_min and not can_force:
                raise UserError(
                    f"已报名 {dep.seats_used} 人低于成团线 {dep.seats_min}，仅管理层可强行确认。")
            dep.state = 'confirmed'

    def action_depart(self):
        for dep in self:
            if dep.state != 'confirmed':
                raise UserError("只有确认成团的发团计划可以发团。")
            dep.state = 'departed'

    def action_settle(self):
        for dep in self:
            if dep.state != 'departed':
                raise UserError("只有已发团的发团计划可以进入结算完成。")
            dep.state = 'settled'

    def action_cancel(self):
        for dep in self:
            if dep.state in ('departed', 'settled', 'merged'):
                raise UserError("已发团/结算/并入的发团计划不可取消。")
            if dep.seats_used:
                raise UserError("发团计划仍有报名占位，先取消相关订单再取消发团计划。")
            dep.state = 'cancel'
