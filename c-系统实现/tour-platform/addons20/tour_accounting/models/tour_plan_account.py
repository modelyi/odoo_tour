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
    analytic_line_ids = fields.One2many(
        'account.analytic.line', 'account_id',
        related='analytic_account_id.line_ids', string='分析行',
        help='承载团分析账户下的分析行；作为收入/成本物化汇总的重算依赖源')

    income_total = fields.Float('收入合计', digits=(16, 2), compute='_compute_from_analytic',
                                store=True, help='← analytic.line 收入类科目汇总 [TDS §4.3]')
    cost_total = fields.Float('成本合计', digits=(16, 2), compute='_compute_from_analytic',
                              store=True, help='← analytic.line 成本类科目汇总 [TDS §4.3]')
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

    # === 应收账龄（BS-12 §8.4 / §5.1）===
    receivable_positive = fields.Float(
        '应收余额(客户欠款)', digits=(16, 2), compute='_compute_receivable_split',
        store=True, help='sum_un_pay > 0 部分，账龄对象 [BS-12 §5.1]')
    receivable_negative = fields.Float(
        '溢缴(客户多付)', digits=(16, 2), compute='_compute_receivable_split',
        store=True, help='sum_un_pay < 0 部分（正数表示溢缴），转预收账款列示 [CAS 37]')

    # 账龄区间余额（compute 自 1122.01 未核销行，date_maturity 到期日）[BS-12 §5.2]
    aging_0_30 = fields.Float('账龄0-30天', digits=(16, 2),
                              compute='_compute_receivable_aging',
                              help='未到期及逾期 ≤30 天的应收（借方余额）')
    aging_31_90 = fields.Float('账龄31-90天', digits=(16, 2),
                               compute='_compute_receivable_aging')
    aging_91_180 = fields.Float('账龄91-180天', digits=(16, 2),
                                compute='_compute_receivable_aging')
    aging_181_365 = fields.Float('账龄181-365天', digits=(16, 2),
                                 compute='_compute_receivable_aging')
    aging_over_365 = fields.Float('账龄>365天', digits=(16, 2),
                                  compute='_compute_receivable_aging')
    overdue_days = fields.Integer('最大逾期天数', compute='_compute_receivable_aging',
                                  help='该团 1122.01 未核销应收行中最大逾期天数（催收/坏账依据）')

    # === 四维账龄分析维度（BS-12 §5.2：按团/线路/销售员/客户）===
    line_id = fields.Many2one('tour.line', string='线路', related='plan_id.line_id',
                              store=True, index=True)
    sales_name = fields.Char('销售归属', related='plan_id.sales_name',
                             store=True, index=True)
    supplier_id = fields.Many2one('res.partner', string='客户', related='plan_id.supplier_id',
                                  store=True, index=True)

    # === 单团毛利口径（BS-19 裁定：差额征税 · 不含税口径）===
    cost_net_total = fields.Float(
        '不含税成本', digits=(16, 2), compute='_compute_profit', store=True,
        help='= 成本合计 ÷(1+r)（r=本企业税率/征收率）；'
             '公司开关 tour_cost_tax_split=True 时 = 成本合计（记账侧已拆税，不再换算）'
             '[BS-19 §二 / 财会2016-22号]')
    profit_tax_incl = fields.Float(
        '毛利(含税口径)', digits=(16, 2), compute='_compute_profit', store=True,
        help='= 含税收入(收入合计×(1+r)) − 含税成本(成本合计)；'
             '业务/源系统核对口径（in_com_quo_sum − out_sum），非权威利润 [BS-19 §一 裁定3]')
    profit = fields.Float('毛利(不含税)', digits=(16, 2), compute='_compute_profit', store=True,
                          help='= 不含税收入 − 不含税成本；唯一权威利润口径 [CAS 14/30 / BS-19 §二]')
    profit_no_shop = fields.Float('毛利(不含税,不含购物)', digits=(16, 2),
                                  compute='_compute_profit', store=True,
                                  help='= (不含税收入 − 购物佣金收入) − 不含税成本')
    profit_margin = fields.Float('毛利率(%)', digits=(8, 2), compute='_compute_profit',
                                 store=True,
                                 help='= 毛利(不含税) ÷ 收入合计 × 100')
    begin_date = fields.Date('出发日期', related='plan_id.begin_date', store=True)

    # === 状态/归属 ===
    state = fields.Selection([
        ('accounting', '核算中'),
        ('settled', '已结算'),
        ('archived', '已归档'),
    ], string='状态', default='accounting', required=True, index=True)
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

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

    @api.depends('plan_id.sum_un_pay')
    def _compute_receivable_split(self):
        """应收正/负分离：sum_un_pay > 0 为账龄对象，< 0 转预收列示 [BS-12 §5.1]。"""
        for rec in self:
            v = rec.plan_id.sum_un_pay if rec.plan_id else 0.0
            rec.receivable_positive = v if v > 0 else 0.0
            rec.receivable_negative = -v if v < 0 else 0.0

    @api.depends('analytic_account_id')
    def _compute_receivable_aging(self):
        """账龄区间余额：compute 自 1122.01 未核销行的 date_maturity（到期日）。

        只计借方余额（amount_residual > 0，客户欠款）；未到期归入 0-30 天。
        账龄数据源 = 记账真相（account.move.line），与业务快照 receivable_positive 可存在差异
        （发票未过账时 1122.01 行尚未生成）[BS-12 §5.2]。
        """
        buckets = ('aging_0_30', 'aging_31_90', 'aging_91_180',
                   'aging_181_365', 'aging_over_365')
        acc = self.env['account.account'].search(
            [('code', '=', self.ACCOUNT_RECEIVABLE_TOUR)], limit=1)
        for rec in self:
            for b in buckets:
                rec[b] = 0.0
            rec.overdue_days = 0
            if not rec.analytic_account_id or not acc:
                continue
            today = fields.Date.context_today(rec)
            lines = self._plan_open_move_lines(
                rec.plan_id, account_ids=[acc.id], reconciled=False)
            for ln in lines:
                residual = ln.amount_residual or 0.0
                if residual <= 0:
                    continue  # 只计客户欠款（借方余额）
                maturity = ln.date_maturity or ln.date
                days = (today - maturity).days if maturity else 0
                if days < 0:
                    days = 0
                if days > rec.overdue_days:
                    rec.overdue_days = days
                if days <= 30:
                    rec.aging_0_30 += residual
                elif days <= 90:
                    rec.aging_31_90 += residual
                elif days <= 180:
                    rec.aging_91_180 += residual
                elif days <= 365:
                    rec.aging_181_365 += residual
                else:
                    rec.aging_over_365 += residual


    @api.depends('analytic_account_id', 'analytic_line_ids.amount')
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

    @api.depends('income_total', 'cost_total', 'income_commission',
                 'company_id.tour_taxpayer_type', 'company_id.tour_vat_rate',
                 'company_id.tour_vat_levy_rate', 'company_id.tour_cost_tax_split')
    def _compute_profit(self):
        """单团毛利：差额征税 · 不含税口径，收入/成本同口径相减 [BS-19 §二]。

        - 总额法（组团）：成本按**本企业税率 r** 不含税化 → 与不含税收入配比
          （财会2016-22号：差额征税按本企业税率、用含税金额统一换算，不分项换算供应商税率）
        - 净额法（代订 biz_mode 41 / 地接）：代收代付走 2241.01 不进 6401 →
          cost_total=0 → profit = income_total（差价不含税），同式自动成立，无需特判
        - profit_tax_incl 为含税管理口径（≠ 权威利润）

        不变量 [BS-19 §一 裁定5]：cost_total 固定为成本分析行净额（含税）。
        若记账侧已拆成本税（res.company.tour_cost_tax_split=True，差额抵减凭证已回写 6401），
        则不再换算，避免双重扣减。两状态由该单开关唯一决定，不得叠加。

        取值修正 [BS-19 §2.3]：用 rec.company_id（非 env.company）取税参，
        保证多主体（各自身份/税率）各自口径正确。
        """
        for rec in self:
            co = rec.company_id or self.env.company
            _tp, rate_pct, _enabled = self._tour_vat_params(co)
            rr = (rate_pct or 0.0) / 100.0
            gross = rec.cost_total or 0.0
            income = rec.income_total or 0.0
            if co.tour_cost_tax_split or not rr:
                cost_net = round(gross, 2)
            else:
                cost_net = round(gross / (1 + rr), 2)
            rec.cost_net_total = cost_net
            rec.profit = round(income - cost_net, 2)
            rec.profit_no_shop = round(
                income - (rec.income_commission or 0.0) - cost_net, 2)
            inc_gross = income * (1 + rr) if rr else income
            rec.profit_tax_incl = round(inc_gross - gross, 2)
            rec.profit_margin = round(
                (income - cost_net) / income * 100.0, 2) if income else 0.0

    # === Stat button counts ===
    invoice_count = fields.Integer('发票数', compute='_compute_related_counts')
    claim_count = fields.Integer('收款数', compute='_compute_related_counts')
    analytic_move_count = fields.Integer('凭证行数', compute='_compute_related_counts')
    dunning_count = fields.Integer('催收数', compute='_compute_related_counts')

    @api.depends('plan_id', 'analytic_account_id')
    def _compute_related_counts(self):
        for rec in self:
            plan = rec.plan_id
            rec.invoice_count = len(plan.invoice_ids) if plan else 0
            rec.claim_count = len(plan.claim_ids) if plan else 0
            rec.analytic_move_count = len(rec.analytic_account_id.line_ids) if rec.analytic_account_id else 0
            rec.dunning_count = self.env['tour.dunning'].search_count(
                [('plan_id', '=', plan.id)]) if plan else 0

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '团队发票',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.plan_id.invoice_ids.ids)],
        }

    def action_view_claims(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '收款认领',
            'res_model': 'tour.payment.claim',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.plan_id.claim_ids.ids)],
        }

    def action_view_analytic_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '分析凭证行',
            'res_model': 'account.analytic.line',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.analytic_account_id.id)],
        }

    def action_view_dunnings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '催收记录',
            'res_model': 'tour.dunning',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.plan_id.id)],
        }

    def action_settle(self):
        for rec in self:
            rec.state = 'settled'

    def action_archive(self):
        for rec in self:
            rec.state = 'archived'

    def action_reopen(self):
        for rec in self:
            rec.state = 'accounting'
