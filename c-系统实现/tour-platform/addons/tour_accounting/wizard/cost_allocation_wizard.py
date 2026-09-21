# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TourCostAllocationWizard(models.TransientModel):
    _name = 'tour.cost.allocation.wizard'
    _description = '执行费用分摊'

    date_from = fields.Date('开始日期', required=True)
    date_to = fields.Date('结束日期', required=True)
    rule_ids = fields.Many2many(
        'tour.cost.allocation.rule', string='分摊规则',
        domain=[('active', '=', True)])
    preview_ids = fields.One2many(
        'tour.cost.allocation.preview', 'wizard_id', string='预览')

    def action_compute_preview(self):
        self.ensure_one()
        self.preview_ids.unlink()
        rules = self.rule_ids or self.env['tour.cost.allocation.rule'].search(
            [('active', '=', True)])
        previews = []
        for rule in rules:
            domain = [
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('account_id', '=', rule.source_account_id.id),
                ('parent_state', '=', 'posted'),
            ]
            lines = self.env['account.move.line'].search(domain)
            total = sum(lines.mapped('debit'))
            if total <= 0:
                continue
            for rline in rule.line_ids:
                amount = round(total * rline.percentage / 100.0, 2)
                if amount > 0:
                    previews.append({
                        'wizard_id': self.id,
                        'rule_id': rule.id,
                        'source_account_id': rule.source_account_id.id,
                        'target_account_id': rline.analytic_account_id.id,
                        'amount': amount,
                    })
        self.env['tour.cost.allocation.preview'].create(previews)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tour.cost.allocation.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_execute(self):
        self.ensure_one()
        if not self.preview_ids:
            self.action_compute_preview()
        rules = self.rule_ids or self.env['tour.cost.allocation.rule'].search(
            [('active', '=', True)])
        for rule in rules:
            domain = [
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('account_id', '=', rule.source_account_id.id),
                ('parent_state', '=', 'posted'),
            ]
            lines = self.env['account.move.line'].search(domain)
            total = sum(lines.mapped('debit'))
            if total <= 0:
                continue
            move_lines = []
            remaining = total
            for idx, rline in enumerate(rule.line_ids):
                if idx == len(rule.line_ids) - 1:
                    credit = round(remaining, 2)
                else:
                    credit = round(total * rline.percentage / 100.0, 2)
                    remaining -= credit
                if credit > 0:
                    move_lines.append((0, 0, {
                        'account_id': rule.source_account_id.id,
                        'name': '分摊 %s' % rule.name,
                        'debit': 0.0,
                        'credit': credit,
                        'analytic_distribution': {
                            str(rline.analytic_account_id.id): 100.0,
                        },
                    }))
            if move_lines:
                move_lines.append((0, 0, {
                    'account_id': rule.source_account_id.id,
                    'name': '分摊 %s' % rule.name,
                    'debit': total,
                    'credit': 0.0,
                }))
                move = self.env['account.move'].create({
                    'journal_id': rule.journal_id.id,
                    'date': self.date_to,
                    'ref': '费用分摊 %s (%s ~ %s)' % (
                        rule.name, self.date_from, self.date_to),
                    'line_ids': move_lines,
                })
                move.action_post()


class TourCostAllocationPreview(models.TransientModel):
    _name = 'tour.cost.allocation.preview'
    _description = '分摊预览'

    wizard_id = fields.Many2one('tour.cost.allocation.wizard', string='Wizard')
    rule_id = fields.Many2one('tour.cost.allocation.rule', string='规则')
    source_account_id = fields.Many2one('account.account', string='来源科目')
    target_account_id = fields.Many2one('account.analytic.account', string='目标分析账户')
    amount = fields.Float('金额')
