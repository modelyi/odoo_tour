# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TourCostAllocationRule(models.Model):
    _name = 'tour.cost.allocation.rule'
    _description = '费用分摊规则'
    _order = 'sequence, id'

    name = fields.Char('规则名称', required=True)
    sequence = fields.Integer('顺序', default=10)
    active = fields.Boolean('启用', default=True)
    source_account_id = fields.Many2one(
        'account.account', string='来源科目', required=True,
        help='需要分摊的费用科目（如 6602 管理费用）')
    allocation_base = fields.Selection([
        ('headcount', '按人头数'),
        ('revenue', '按收入比例'),
        ('fixed', '固定比例'),
    ], string='分摊基础', required=True, default='headcount')
    target_plan_id = fields.Many2one(
        'account.analytic.plan', string='目标分析计划',
        required=True,
        help='分摊到哪个分析计划的账户（通常为「成本中心」）')
    journal_id = fields.Many2one(
        'account.journal', string='日记账', required=True,
        help='分摊凭证使用的日记账')
    line_ids = fields.One2many(
        'tour.cost.allocation.rule.line', 'rule_id', string='分摊明细')
    company_id = fields.Many2one(
        'res.company', string='公司',
        default=lambda self: self.env.company)


class TourCostAllocationRuleLine(models.Model):
    _name = 'tour.cost.allocation.rule.line'
    _description = '费用分摊规则明细'
    _order = 'percentage desc'

    rule_id = fields.Many2one(
        'tour.cost.allocation.rule', string='规则', required=True,
        ondelete='cascade')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='目标分析账户', required=True,
        help='分摊目标的分析账户（如某部门的成本中心）')
    percentage = fields.Float('比例(%)', required=True, help='分摊百分比')
