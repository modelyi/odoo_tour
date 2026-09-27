# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaAsset(models.Model):
    """固定资产卡片：直线法 + 残值率，月折旧额 = 原值×(1−残值率)÷折旧月数。

    状态：draft（草稿）→ in_use（在用，开始计提）→ disposed（已处置，停止计提）。
    凭证由 ta.asset.depreciation 按月生成，本卡片只存台账口径。
    """
    _name = 'ta.asset'
    _description = '固定资产卡片'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'code'

    name = fields.Char(string='资产名称', required=True, tracking=True)
    code = fields.Char(string='资产编号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.asset') or '/')
    category = fields.Selection([
        ('vehicle', '车辆'),
        ('office', '办公设备'),
        ('furniture', '家具家电'),
        ('electronic', '电子设备'),
        ('other', '其他'),
    ], string='资产类别', required=True, default='other', tracking=True)
    acquisition_date = fields.Date(string='购置日期', required=True,
                                   default=fields.Date.context_today, tracking=True)
    cost = fields.Monetary(string='资产原值', required=True, currency_field='currency_id', tracking=True)
    residual_rate = fields.Float(string='残值率(%)', default=5.0, required=True)
    depreciation_months = fields.Integer(string='折旧月数', required=True, default=48)
    monthly_depreciation = fields.Float(
        compute='_compute_depreciation', string='月折旧额', store=True)
    accumulated_depreciation = fields.Float(
        compute='_compute_depreciation', string='累计折旧', store=True)
    book_value = fields.Float(
        compute='_compute_depreciation', string='账面净值', store=True)
    depreciation_line_ids = fields.One2many('ta.asset.depreciation', 'asset_id', string='折旧记录')
    state = fields.Selection([
        ('draft', '草稿'),
        ('in_use', '在用'),
        ('disposed', '已处置'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    currency_id = fields.Many2one('res.currency', string='币种',
                                  default=lambda self: self.env.company.currency_id)
    note = fields.Char(string='备注')

    _cost_positive = models.Constraint('check(cost > 0)', '资产原值必须为正。')
    _months_positive = models.Constraint(
        'check(depreciation_months > 0 and residual_rate >= 0 and residual_rate < 100)',
        '折旧月数须为正，残值率须在 0（含）~100（不含）之间。')

    @api.depends('cost', 'residual_rate', 'depreciation_months',
                 'depreciation_line_ids.amount')
    def _compute_depreciation(self):
        for asset in self:
            base = asset.cost * (1.0 - asset.residual_rate / 100.0)
            monthly = round(base / asset.depreciation_months, 2) if asset.depreciation_months else 0.0
            asset.monthly_depreciation = monthly
            asset.accumulated_depreciation = sum(asset.depreciation_line_ids.mapped('amount'))
            asset.book_value = asset.cost - asset.accumulated_depreciation

    @api.constrains('acquisition_date')
    def _check_acquisition_date(self):
        # 会计数据不可直改：已有折旧记录的资产不得回改购置日期
        for asset in self:
            if asset.depreciation_line_ids:
                raise UserError(f"资产「{asset.name}」已有折旧记录，不能修改购置日期。")

    def action_validate(self):
        for asset in self:
            if asset.state != 'draft':
                raise UserError("只有草稿卡片可以启用。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("启用资产卡片需要会计权限。")
            asset.state = 'in_use'

    def action_dispose(self):
        for asset in self:
            if asset.state != 'in_use':
                raise UserError("只有在用资产可以处置。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("处置资产需要会计权限。")
            asset.state = 'disposed'

    def action_back_to_draft(self):
        for asset in self:
            if asset.state != 'disposed' or asset.depreciation_line_ids:
                raise UserError("仅无折旧记录的已处置卡片可退回草稿。")
            asset.state = 'draft'
