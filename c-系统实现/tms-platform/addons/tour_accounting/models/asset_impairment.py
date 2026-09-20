# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AssetImpairment(models.Model):
    _name = 'asset.impairment'
    _description = 'Asset Impairment'
    _order = 'date desc, id desc'

    name = fields.Char(string='编号', required=True, copy=False,
                       default=lambda self: _('New'))
    asset_id = fields.Many2one('account.asset.asset', string='资产',
                               required=True, ondelete='cascade')
    date = fields.Date(string='日期', required=True,
                       default=fields.Date.context_today)
    amount = fields.Float(string='减值金额', required=True)
    reason = fields.Text(string='减值原因')
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('posted', '已过账'),
        ('cancelled', '已取消'),
    ], string='状态', default='draft', required=True)
    move_id = fields.Many2one('account.move', string='会计凭证',
                              copy=False, readonly=True)
    company_id = fields.Many2one('res.company', string='公司',
                                 required=True,
                                 default=lambda self: self.env.company)
    notes = fields.Text(string='备注')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    move_count = fields.Integer('凭证数', compute='_compute_move_count')

    @api.depends('move_id')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = 1 if rec.move_id else 0

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            return {'type': 'ir.actions.act_window', 'name': '凭证', 'res_model': 'account.move', 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}
        return {
            'type': 'ir.actions.act_window',
            'name': '减值凭证',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'asset.impairment') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for impairment in self:
            if impairment.asset_id.state not in ('open', 'paused'):
                raise UserError(_('只能对运行中或已暂停的资产进行减值'))
            impairment.state = 'confirmed'

    def action_post(self):
        for impairment in self:
            if impairment.state != 'confirmed':
                raise UserError(_('请先确认减值记录'))
            impairment._create_move()
            impairment.state = 'posted'

    def action_cancel(self):
        for impairment in self:
            if impairment.move_id:
                if impairment.move_id.state == 'posted':
                    impairment.move_id.button_cancel()
                impairment.move_id.unlink()
            impairment.state = 'cancelled'

    def action_draft(self):
        for impairment in self:
            impairment.state = 'draft'

    def _create_move(self):
        self.ensure_one()
        asset = self.asset_id
        if not asset.account_depreciation_expense_id:
            raise UserError(_('资产未配置费用科目'))
        if not asset.account_asset_id:
            raise UserError(_('资产未配置资产科目'))

        move_vals = {
            'journal_id': asset.journal_id.id,
            'date': self.date,
            'ref': self.name,
            'line_ids': [
                (0, 0, {
                    'name': self.name,
                    'account_id': asset.account_depreciation_expense_id.id,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': self.name,
                    'account_id': asset.account_asset_id.id,
                    'debit': 0.0,
                    'credit': self.amount,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.write({'move_id': move.id})
