# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TaBizMode(models.Model):
    _name = 'ta.biz.mode'
    _description = '业务模式码'
    _order = 'code_int, code'
    _inherit = ['ta.mixin']

    name = fields.Char(string='模式名称', required=True, translate=True)
    code = fields.Char(string='码值', required=True, index=True)
    code_int = fields.Integer(compute='_compute_code_int', store=True)
    is_alias = fields.Boolean(string='别名码', help='与其他码值同义（源自易途 BizModeID 的历史别名）。')
    alias_of = fields.Many2one('ta.biz.mode', string='指向正式码', domain="[('is_alias', '=', False)]")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='公司', default=lambda self: self.env.company,
        help='留空表示全公司共享的系统字典。')
    partner_share = fields.Boolean(
        string='计调资源侧可见', default=False,
        help='勾选后允许在计调资源条目中选择该模式。')
    description = fields.Char(translate=True)

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        '同一公司下业务模式码不能重复。')

    @api.depends('code')
    def _compute_code_int(self):
        for rec in self:
            try:
                rec.code_int = int(rec.code or '0')
            except ValueError:
                rec.code_int = 0

    @api.constrains('is_alias', 'alias_of')
    def _check_alias(self):
        for rec in self:
            if rec.is_alias and not rec.alias_of:
                raise ValidationError("别名码必须指向一个正式码。")
            if not rec.is_alias and rec.alias_of:
                raise ValidationError("只有别名码可以设置指向正式码。")
