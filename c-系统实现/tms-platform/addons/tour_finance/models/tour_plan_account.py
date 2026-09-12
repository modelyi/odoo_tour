# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourPlanAccount(models.Model):
    _name = 'tour.plan.account'
    _description = '单团核算'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # === 关联 ===
    plan_id = fields.Many2one('tour.plan', string='团队订单', required=True,
                              index=True, ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True, index=True,
                            help='团号冗余，加速检索')
    analytic_account_id = fields.Many2one('account.analytic.account', string='分析账户',
                                          help='一团一核算：团号即分析账户名 [CAS 30]')
    biz_mode = fields.Selection(related='plan_id.biz_mode', string='业务模式', store=True,
                                help='决定总额法/净额法')

    # === 核算金额 ===
    income_total = fields.Float('收入合计', digits=(16, 2), compute='_compute_from_plan',
                                store=True, help='compute ← plan.in_sum')
    income_commission = fields.Float('购物佣金收入', digits=(16, 2),
                                     help='购物佣金收入（经营收入，不可差额扣除）')
    cost_total = fields.Float('成本合计', digits=(16, 2), compute='_compute_from_plan',
                              store=True, help='compute ← plan.out_sum')
    cost_deductible = fields.Float('可扣除成本', digits=(16, 2),
                                   help='差额征税可扣除成本 [财税2016-36号]')
    cost_non_deductible = fields.Float('不可扣除成本', digits=(16, 2),
                                       help='不可差额扣除成本（导服/保险/购物等）')
    receivable = fields.Float('应收余额', digits=(16, 2), compute='_compute_from_plan',
                              store=True, help='compute ← plan.sum_un_pay')
    prepaid = fields.Float('预收余额', digits=(16, 2), help='预收余额（← 收款-确认）')
    invoice_gap = fields.Float('发票缺口', digits=(16, 2), compute='_compute_from_plan',
                               store=True, help='compute ← plan.un_invoice_money 🔴F-03')
    profit = fields.Float('利润', digits=(16, 2), compute='_compute_profit', store=True,
                          help='= 收入合计 - 成本合计')
    profit_no_shop = fields.Float('利润(不含购物)', digits=(16, 2), compute='_compute_profit',
                                  store=True, help='= 收入(不含购物) - 成本合计')

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

    @api.depends('plan_id.in_sum', 'plan_id.out_sum',
                 'plan_id.sum_un_pay', 'plan_id.un_invoice_money')
    def _compute_from_plan(self):
        for rec in self:
            p = rec.plan_id
            rec.income_total = p.in_sum if p else 0.0
            rec.cost_total = p.out_sum if p else 0.0
            rec.receivable = p.sum_un_pay if p else 0.0
            rec.invoice_gap = p.un_invoice_money if p else 0.0

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
