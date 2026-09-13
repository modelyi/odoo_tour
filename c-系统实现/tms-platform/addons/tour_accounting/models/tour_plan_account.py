# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourPlanAccount(models.Model):
    _name = 'tour.plan.account'
    _description = '单团核算'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.accounting.mixin']
    _order = 'id desc'

    # === 关联 ===
    plan_id = fields.Many2one('tour.plan', string='团队订单', required=True,
                              index=True, ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True, index=True,
                            help='团号冗余，加速检索')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='分析账户', related='plan_id.analytic_account_id',
        store=True, index=True,
        help='一团一核算：团号即分析账户名，记账以 analytic 为准 [BS-10 §六]')
    biz_mode = fields.Selection(related='plan_id.biz_mode', string='业务模式', store=True,
                                help='决定总额法/净额法')

    # === 核算金额（Phase 2：由 account.analytic.line 派生，不再取 plan.* 快照）===
    income_total = fields.Float('收入合计', digits=(16, 2), compute='_compute_from_analytic',
                                help='← analytic.line 收入类科目汇总 [TDS §4.3]')
    cost_total = fields.Float('成本合计', digits=(16, 2), compute='_compute_from_analytic',
                              help='← analytic.line 成本类科目汇总 [TDS §4.3]')
    income_commission = fields.Float('购物佣金收入', digits=(16, 2),
                                     help='购物佣金收入（经营收入，不可差额扣除）')
    cost_deductible = fields.Float('可扣除成本', digits=(16, 2), compute='_compute_vat_split',
                                   help='← analytic.line 可扣除科目(tour_vat_deductible=True)汇总 [BS-11 §8.2]')
    cost_non_deductible = fields.Float('不可扣除成本', digits=(16, 2), compute='_compute_vat_split',
                                       help='← analytic.line 不可扣除科目汇总 [BS-11 §8.2]')
    vat_deductible_total = fields.Float('差额扣除基数(含税)', digits=(16, 2),
                                        compute='_compute_vat_fields',
                                        help='= max(0, 可扣除成本 - 发票缺口)，申报附列资料三 [BS-11 §8.3/§十一]')
    vat_deduct_amount = fields.Float('销项税额抵减额', digits=(16, 2), compute='_compute_vat_fields',
                                     help='= 差额扣除基数 ÷(1+r)×r [财会2016-22号]')
    vat_output_amount = fields.Float('全额销项税额', digits=(16, 2), compute='_compute_vat_fields',
                                     help='≈ 收入(不含税)×r，申报销项税额栏 [BS-11 §十一]')
    vat_payable = fields.Float('净应纳增值税', digits=(16, 2), compute='_compute_vat_fields',
                               help='= 全额销项税额 - 销项税额抵减 [BS-11 §十一]')
    receivable = fields.Float('应收余额', digits=(16, 2), compute='_compute_from_plan',
                              store=True, help='compute ← plan.sum_un_pay（业务口径快照）')
    prepaid = fields.Float('预收余额', digits=(16, 2), compute='_compute_from_analytic',
                           help='← 该团未核销预收（2203.01）残值 [TDS §4.3]')
    invoice_gap = fields.Float('发票缺口', digits=(16, 2), compute='_compute_from_plan',
                               store=True, help='compute ← plan.un_invoice_money 🔴F-03')
    profit = fields.Float('利润', digits=(16, 2), compute='_compute_profit',
                          help='= 收入合计 - 成本合计')
    profit_no_shop = fields.Float('利润(不含购物)', digits=(16, 2), compute='_compute_profit',
                                  help='= 收入(不含购物) - 成本合计')

    # === 状态/归属 ===
    state = fields.Selection([
        ('accounting', '核算中'),
        ('settled', '已结算'),
        ('archived', '已归档'),
    ], string='状态', default='accounting', required=True, index=True)
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    _uniq_plan = models.Constraint(
        'unique(plan_id)',
        '该团队订单已存在核算台账',
    )

    @api.depends('plan_id.sum_un_pay', 'plan_id.un_invoice_money')
    def _compute_from_plan(self):
        """应收余额 / 发票缺口：业务口径快照（保留），非记账依据。"""
        for rec in self:
            p = rec.plan_id
            rec.receivable = p.sum_un_pay if p else 0.0
            rec.invoice_gap = p.un_invoice_money if p else 0.0

    def _compute_from_analytic(self):
        """收入/成本/预收：从 account.analytic.line / move.line 派生（记账真相）。"""
        for rec in self:
            income, cost = 0.0, 0.0
            if rec.analytic_account_id:
                income, cost = self._plan_analytic_balance(rec.plan_id)
            rec.income_total = income
            rec.cost_total = cost
            rec.prepaid = self._plan_prepay_balance(rec.plan_id) if rec.plan_id else 0.0

    @api.depends('analytic_account_id')
    def _compute_vat_split(self):
        """可扣除/不可扣除成本：按 tour_vat_deductible 从分析行归集 [BS-11 §8.2]。"""
        for rec in self:
            if rec.analytic_account_id:
                deductible, non_ded = self._plan_cost_vat_split(rec.plan_id)
                rec.cost_deductible = deductible
                rec.cost_non_deductible = non_ded
            else:
                rec.cost_deductible = rec.cost_non_deductible = 0.0

    @api.depends('analytic_account_id', 'income_total', 'cost_deductible', 'invoice_gap')
    def _compute_vat_fields(self):
        """差额征税归集：扣除基数 / 抵减额 / 全额销项 / 净应纳 [BS-11 §十一]。"""
        for rec in self:
            _tp, rate_pct, _en = self._tour_vat_params()
            r = rate_pct / 100.0
            rec.vat_deductible_total = max(
                0.0, (rec.cost_deductible or 0.0) - (rec.invoice_gap or 0.0))
            rec.vat_deduct_amount = round(rec.vat_deductible_total / (1 + r) * r, 2) if r else 0.0
            rec.vat_output_amount = round((rec.income_total or 0.0) * r, 2)
            rec.vat_payable = round(rec.vat_output_amount - rec.vat_deduct_amount, 2)

    @api.depends('income_total', 'cost_total', 'income_commission')
    def _compute_profit(self):
        for rec in self:
            rec.profit = rec.income_total - rec.cost_total
            rec.profit_no_shop = (rec.income_total - rec.income_commission) - rec.cost_total

    def action_settle(self):
        for rec in self:
            rec.state = 'settled'

    def action_archive(self):
        for rec in self:
            rec.state = 'archived'

    def action_reopen(self):
        for rec in self:
            rec.state = 'accounting'
