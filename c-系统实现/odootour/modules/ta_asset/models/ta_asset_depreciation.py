# -*- coding: utf-8 -*-
import calendar
import re

from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaAssetDepreciation(models.Model):
    """按月折旧记录：(资产, 期间) 唯一 → 幂等；生成凭证 借折旧费 / 贷累计折旧。"""
    _name = 'ta.asset.depreciation'
    _description = '资产折旧记录'
    _inherit = ['ta.mixin']
    _order = 'period desc, asset_id'

    asset_id = fields.Many2one('ta.asset', string='资产', required=True, ondelete='cascade')
    period = fields.Char(string='期间(YYYY-MM)', required=True)
    amount = fields.Monetary(string='折旧额', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='asset_id.currency_id', store=True)
    asset_name = fields.Char(related='asset_id.name', string='资产名称', store=True)
    move_id = fields.Many2one('account.move', string='折旧凭证', readonly=True, copy=False)

    _asset_period_uniq = models.Constraint(
        'unique(asset_id, period)', '同一资产同一期间只能计提一次（幂等保护）。')

    @api.constrains('period')
    def _check_period_format(self):
        for rec in self:
            if not re.fullmatch(r'\d{4}-\d{2}', rec.period or ''):
                raise UserError("期间格式须为 YYYY-MM。")

    def action_create_move(self):
        """计提并过账凭证；已生成凭证的记录跳过（幂等）。"""
        icp = self.env['ir.config_parameter'].sudo()
        company = self.env.company
        dep_account = self.env['account.account'].browse(
            icp.get_int('ta_asset.depreciation_account_id', 0)).exists() \
            or company.expense_account_id
        accum_account = self.env['account.account'].browse(
            icp.get_int('ta_asset.accumulated_account_id', 0)).exists()
        if not dep_account:
            raise UserError("未设置折旧费用科目（旅行社管理→设置→固定资产）。")
        if not accum_account:
            raise UserError("未设置累计折旧科目（旅行社管理→设置→固定资产）。")
        journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1) \
            or self.env['account.journal'].search(
                [('company_id', '=', company.id)], limit=1)
        if not journal:
            raise UserError("当前公司没有可用日记账。")
        for rec in self:
            if rec.move_id:
                continue
            year, month = (int(x) for x in rec.period.split('-'))
            date = '%s-%02d-%02d' % (year, month, calendar.monthrange(year, month)[1])
            move = self.env['account.move'].create({
                'journal_id': journal.id,
                'date': date,
                'ref': f"折旧 {rec.asset_id.code} {rec.period}",
                'line_ids': [
                    (0, 0, {'name': f"固定资产折旧 {rec.asset_name} {rec.period}",
                            'account_id': dep_account.id, 'debit': rec.amount}),
                    (0, 0, {'name': f"累计折旧 {rec.asset_name}",
                            'account_id': accum_account.id, 'credit': rec.amount}),
                ],
            })
            move.action_post()
            rec.move_id = move
        return True


class TaAssetDepreciationBatch(models.TransientModel):
    """一键计提：生成截至上月的全部未提折旧记录（幂等），并可顺带过账凭证。"""
    _name = 'ta.asset.depreciate.wizard'
    _description = '批量计提折旧向导'

    period_to = fields.Char(string='计提至期间(YYYY-MM)', required=True)
    post_moves = fields.Boolean(string='同时生成并过账凭证', default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        from datetime import date, timedelta
        last_month_end = date.today().replace(day=1) - timedelta(days=1)
        if 'period_to' in fields_list:
            res['period_to'] = last_month_end.strftime('%Y-%m')
        return res

    def action_run(self):
        self.ensure_one()
        if not re.fullmatch(r'\d{4}-\d{2}', self.period_to or ''):
            raise UserError("期间格式须为 YYYY-MM。")
        if not self.env.user.has_group('ta_base.group_ta_accountant'):
            raise AccessError("计提折旧需要会计权限。")
        year, month = (int(x) for x in self.period_to.split('-'))
        assets = self.env['ta.asset'].search([('state', '=', 'in_use')])
        made = self.env['ta.asset.depreciation']
        for asset in assets:
            # 起点 = 购置日期当月
            ay, am = asset.acquisition_date.year, asset.acquisition_date.month
            existing = set(asset.depreciation_line_ids.mapped('period'))
            accumulated = asset.accumulated_depreciation
            steps = (year - ay) * 12 + (month - am) + 1
            for i in range(steps):
                py, pm = ay + (am - 1 + i) // 12, (am - 1 + i) % 12 + 1
                p = '%04d-%02d' % (py, pm)
                if p in existing:
                    continue
                remaining = round(asset.cost * (1 - asset.residual_rate / 100.0)
                                  - accumulated, 2)
                amount = min(asset.monthly_depreciation, max(remaining, 0.0))
                if amount <= 0:
                    break
                made |= self.env['ta.asset.depreciation'].create({
                    'asset_id': asset.id, 'period': p, 'amount': amount})
                accumulated = round(accumulated + amount, 2)
        if made and self.post_moves:
            made.action_create_move()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if made else 'warning',
                'title': '计提完成',
                'message': f'新增 {len(made)} 条折旧记录（期间截至 {self.period_to}）。'
                           if made else '没有需要计提的折旧（资产均为空或已提满）。',
                'sticky': False,
            },
        }

    @api.model
    def cron_run_depreciate(self):
        """月度自动计提（cron 入口）：计提至上月并过账。"""
        from datetime import date, timedelta
        last = (date.today().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        self.sudo().create({'period_to': last, 'post_moves': True}).action_run()
        return True
