# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class TaPerCapitaLine(models.Model):
    """导游人均线（BS-08 §4.7 / P1-3）：按线路/购物店维度配置基础线、优秀线，
    三档分成比例（基础/标准/提高）；空档位回退司陪导协议 share_rate。

    匹配规则（从具体到宽泛取第一条生效配置）：
    ① 线路+购物店 → ② 仅线路 → ③ 仅购物店 → ④ 全局（线路/购物店均空）。
    人均线考核仅针对导游（§4.7）；司机/陪同始终用其协议分成比例。
    """
    _name = 'ta.per.capita.line'
    _description = '导游人均线'
    _inherit = ['ta.mixin']
    _order = 'id desc'

    name = fields.Char(string='说明', compute='_compute_name', store=True)
    line_id = fields.Many2one('ta.route', string='线路', ondelete='restrict',
                              help='按线路配置（可选）；留空表示全线路。')
    shop_id = fields.Many2one('res.partner', string='购物店', ondelete='restrict',
                              domain="[('supplier_rank', '>', 0)]",
                              help='按购物店配置（可选）；留空表示全购物店。')
    base_line = fields.Float(string='基础人均线', required=True, digits=(15, 2),
                             help='人均购物 < 基础线 → 基础分成比例。')
    excellent_line = fields.Float(string='优秀人均线', required=True, digits=(15, 2),
                                  help='人均购物 ≥ 优秀线 → 提高分成比例。')
    base_rate = fields.Float(string='基础分成比例(%)', digits=(5, 2),
                             help='留空（或 0）回退司陪导协议 share_rate（BS-08 §4.7）。')
    standard_rate = fields.Float(string='标准分成比例(%)', digits=(5, 2),
                                 help='留空（或 0）回退司陪导协议 share_rate（BS-08 §4.7）。')
    excellent_rate = fields.Float(string='提高分成比例(%)', digits=(5, 2),
                                  help='留空（或 0）回退司陪导协议 share_rate（BS-08 §4.7）。')
    state = fields.Selection([
        ('draft', '草稿'),
        ('active', '生效'),
        ('inactive', '已失效'),
    ], string='状态', default='draft', required=True, copy=False, tracking=True)
    note = fields.Char(string='备注')

    @api.depends('line_id', 'shop_id', 'base_line', 'excellent_line')
    def _compute_name(self):
        for r in self:
            parts = []
            if r.line_id:
                parts.append(f"线路[{r.line_id.name}]")
            if r.shop_id:
                parts.append(f"购物店[{r.shop_id.name}]")
            if not r.line_id and not r.shop_id:
                parts.append("全局")
            parts.append(f"{r.base_line:g}/{r.excellent_line:g}")
            r.name = ' '.join(parts)

    @api.constrains('base_line', 'excellent_line')
    def _check_lines(self):
        for r in self:
            if r.base_line < 0:
                raise ValidationError('基础人均线不能为负。')
            if r.excellent_line <= r.base_line:
                raise ValidationError('优秀人均线必须大于基础人均线（BS-08 §4.7）。')

    def action_active(self):
        for r in self:
            if r.state != 'draft':
                raise UserError('只有草稿配置可以生效。')
            r.state = 'active'

    def action_inactive(self):
        for r in self:
            if r.state != 'active':
                raise UserError('只有生效配置可以置为已失效。')
            r.state = 'inactive'

    @api.model
    def _match_line(self, line_id=None, shop_id=None):
        """BS-08 §4.7 匹配（从具体到宽泛取第一条生效配置）。"""
        base = [('state', '=', 'active')]
        if line_id and shop_id:
            hit = self.search(base + [('line_id', '=', line_id), ('shop_id', '=', shop_id)],
                              limit=1, order='id desc')
            if hit:
                return hit
        if line_id:
            hit = self.search(base + [('line_id', '=', line_id), ('shop_id', '=', False)],
                              limit=1, order='id desc')
            if hit:
                return hit
        if shop_id:
            hit = self.search(base + [('line_id', '=', False), ('shop_id', '=', shop_id)],
                              limit=1, order='id desc')
            if hit:
                return hit
        return self.search(base + [('line_id', '=', False), ('shop_id', '=', False)],
                           limit=1, order='id desc')

    def _tier_rate(self, per_capita):
        """返回 (档位比例, 档位名)；比例未配置（空/0）→ (None, 档位名)，引擎回退协议。"""
        self.ensure_one()
        if per_capita < self.base_line:
            return (self.base_rate or None, '基础')
        if per_capita < self.excellent_line:
            return (self.standard_rate or None, '标准')
        return (self.excellent_rate or None, '优秀')


class TaPerCapitaCalc(models.Model):
    """人均算法设置（BS-08 §4.8 / P1-3）：简单平均 / 加权平均 / 分段计算，
    取整方式（四舍五入/向上/向下）与小数位数；同一（线路,购物店）维度只允许
    一个生效配置。

    匹配规则同 §4.7：线路+购物店 → 仅线路 → 仅购物店 → 全局。
    分段计算：按购物店维度查更具体配置（线路+购物店 → 仅购物店），
    仍无更具体配置时按简单平均兜底。
    """
    _name = 'ta.per.capita.calc'
    _description = '人均算法设置'
    _inherit = ['ta.mixin']
    _order = 'id desc'

    name = fields.Char(string='说明', compute='_compute_name', store=True)
    line_id = fields.Many2one('ta.route', string='线路', ondelete='restrict',
                              help='按线路配置（可选）；留空表示全线路。')
    shop_id = fields.Many2one('res.partner', string='购物店', ondelete='restrict',
                              domain="[('supplier_rank', '>', 0)]",
                              help='按购物店配置（可选）；留空表示全购物店。')
    calc_mode = fields.Selection([
        ('simple', '简单平均'),
        ('weighted', '加权平均'),
        ('segment', '分段计算'),
    ], string='计算方式', required=True, default='simple',
        help='简单平均=购物金额÷客人数；加权平均=按报名名单价别加权'
             '（成人1.0/儿童0.5，老人类型暂缺按1.0兜底）；'
             '分段计算=按购物店维度查更具体配置。')
    round_way = fields.Selection([
        ('half_up', '四舍五入'),
        ('up', '向上取整'),
        ('down', '向下取整'),
    ], string='取整方式', required=True, default='half_up')
    decimal_places = fields.Integer(string='小数位数', required=True, default=2)
    state = fields.Selection([
        ('draft', '草稿'),
        ('active', '生效'),
        ('inactive', '已失效'),
    ], string='状态', default='draft', required=True, copy=False, tracking=True)
    note = fields.Char(string='备注')

    @api.depends('line_id', 'shop_id', 'calc_mode', 'round_way', 'decimal_places')
    def _compute_name(self):
        mode_map = dict(self._fields['calc_mode'].selection)
        round_map = dict(self._fields['round_way'].selection)
        for r in self:
            parts = []
            if r.line_id:
                parts.append(f"线路[{r.line_id.name}]")
            if r.shop_id:
                parts.append(f"购物店[{r.shop_id.name}]")
            if not r.line_id and not r.shop_id:
                parts.append("全局")
            parts.append(mode_map.get(r.calc_mode, ''))
            parts.append(f"{round_map.get(r.round_way, '')}{r.decimal_places}位")
            r.name = ' '.join(p for p in parts if p)

    @api.constrains('decimal_places')
    def _check_decimal_places(self):
        for r in self:
            if not 0 <= r.decimal_places <= 6:
                raise ValidationError('小数位数必须在 0-6 之间。')

    def action_active(self):
        for r in self:
            if r.state != 'draft':
                raise UserError('只有草稿配置可以生效。')
            dup = self.search([
                ('state', '=', 'active'),
                ('line_id', '=', r.line_id.id),
                ('shop_id', '=', r.shop_id.id),
                ('id', '!=', r.id),
            ], limit=1)
            if dup:
                raise UserError(
                    f"同一（线路、购物店）维度已有生效算法配置「{dup.name}」，"
                    f"请先将其置为已失效。")
            r.state = 'active'

    def action_inactive(self):
        for r in self:
            if r.state != 'active':
                raise UserError('只有生效配置可以置为已失效。')
            r.state = 'inactive'

    @api.model
    def _resolve_calc(self, line_id=None, shop_id=None):
        """返回生效算法配置（可空）；引擎据 calc_mode/round_way/decimal_places 计算。
        分段计算按购物店维度取更具体配置（线路+购物店 → 仅购物店），
        仍无更具体配置时引擎按简单平均兜底。"""
        base = [('state', '=', 'active')]

        def _first(dom):
            return self.search(base + dom, limit=1, order='id desc')

        hit = self.browse()
        if line_id and shop_id:
            hit = _first([('line_id', '=', line_id), ('shop_id', '=', shop_id)])
        if not hit and line_id:
            hit = _first([('line_id', '=', line_id), ('shop_id', '=', False)])
        if not hit and shop_id:
            hit = _first([('line_id', '=', False), ('shop_id', '=', shop_id)])
        if not hit:
            hit = _first([('line_id', '=', False), ('shop_id', '=', False)])
        if not hit:
            return self.browse()
        if hit.calc_mode == 'segment':
            sub = self.browse()
            if line_id and shop_id:
                sub = _first([('line_id', '=', line_id), ('shop_id', '=', shop_id)])
            if not sub and shop_id:
                sub = _first([('line_id', '=', False), ('shop_id', '=', shop_id)])
            hit = sub or hit
        return hit
