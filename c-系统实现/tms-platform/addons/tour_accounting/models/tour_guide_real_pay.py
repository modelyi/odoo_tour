# -*- coding: utf-8 -*-
"""导游报账单 + 报销明细行 [TDS §2.2 / BS-06 §5.2/§5.4 / BS-15 §3]。

链路：
- 有借款冲抵：报账提交（待审核）→ 报账审核（已审核，生成冲抵凭证
    借 6401.xx 成本 / 贷 1221.01 冲抵借款，差额补款/退款）→ 已结算。
- 纯报销（无借款）两段式：审核（已审核，生成 借 6401.xx 成本 / 贷 2241.06 应付员工）
    → 出纳付款（已结算，生成 借 2241.06 / 贷 1002），审批≠付款分离 [BS-15 §3]。
"""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourGuideRealPay(models.Model):
    _name = 'tour.guide.real.pay'
    _description = '导游报账单'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.accounting.mixin']
    _order = 'report_date desc, id desc'

    # === 标识 ===
    name = fields.Char('报账单号', required=True, copy=False, default='新建',
                       help='自动流水，如 BZ-000123')

    # === 业务关联 ===
    # 财务人事线：报销人维度挂 hr.employee；guide_id 保留为可空冗余
    employee_id = fields.Many2one('hr.employee', string='报销人（员工）', index=True,
                                  ondelete='restrict',
                                  default=lambda self: self.env.user.employee_id.id or False,
                                  help='借款/报销/佣金统一挂员工维度；凭证往来方取员工的工作联系人；'
                                       '员工自助默认取当前登录用户的员工档案')
    guide_id = fields.Many2one('tour.guide', string='导游', required=False,
                               index=True, ondelete='restrict')
    plan_id = fields.Many2one('tour.plan', string='团队', required=False,
                              index=True, ondelete='restrict',
                              help='挂团报账必填；员工自身差旅/费用报销可不挂团（不可差额扣除）')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    loan_id = fields.Many2one(
        'tour.guide.loan', string='关联借款单', index=True, ondelete='restrict',
        domain="[('employee_id', '=', employee_id), ('state', '=', 'disbursed')]",
        help='报账冲抵的借款单（须已放款）；留空为纯报销（无借款，走两段式应付）')

    # === 报账明细 ===
    expense_line_ids = fields.One2many('tour.guide.expense.line', 'real_pay_id',
                                       string='报销明细')
    total_amount = fields.Float('报账总额', digits=(16, 2),
                                compute='_compute_total', store=True)
    loan_amount = fields.Float('借款金额', digits=(16, 2),
                               compute='_compute_total', store=True)
    balance = fields.Float('差额(报账-借款)', digits=(16, 2),
                           compute='_compute_total', store=True,
                           help='>0 公司补款；<0 导游退款；=0 完全冲抵')

    # === 状态机（待审核/已审核/已结算）===
    state = fields.Selection([
        ('draft', '待审核'),
        ('audited', '已审核'),
        ('settled', '已结算'),
    ], string='状态', default='draft', required=True, index=True, tracking=True)
    auditor_id = fields.Many2one('res.users', string='审核人')
    audit_date = fields.Datetime('审核时间')
    report_date = fields.Date('报账日期', default=fields.Date.context_today, required=True)

    # === 会计凭证回链 ===
    move_id = fields.Many2one('account.move', string='冲抵凭证', copy=False,
                              ondelete='restrict', index=True)
    move_state = fields.Selection(related='move_id.state', string='凭证状态')
    # 纯报销两段式：审核凭证（借费用/贷 2241.06）之外的出纳付款凭证（借 2241.06/贷 1002）
    payment_move_id = fields.Many2one('account.move', string='付款凭证', copy=False,
                                      ondelete='restrict', index=True,
                                      help='纯报销出纳付款凭证（借 2241.06 / 贷 1002）')
    payment_move_state = fields.Selection(related='payment_move_id.state', string='付款凭证状态')
    payer_id = fields.Many2one('res.users', string='付款人')
    pay_date = fields.Datetime('付款时间')

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    _uniq_real_pay_name = models.Constraint('unique(name)', '报账单号已存在')

    @api.onchange('guide_id')
    def _onchange_guide_id(self):
        if self.guide_id and self.guide_id.employee_id:
            self.employee_id = self.guide_id.employee_id

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and not self.guide_id:
            guide = self.env['tour.guide'].search(
                [('employee_id', '=', self.employee_id.id)], limit=1)
            if guide:
                self.guide_id = guide

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.guide.real.pay') or '新建'
            if not vals.get('employee_id') and vals.get('guide_id'):
                guide = self.env['tour.guide'].browse(vals['guide_id'])
                if guide.employee_id:
                    vals['employee_id'] = guide.employee_id.id
        return super().create(vals_list)

    @api.depends('expense_line_ids', 'expense_line_ids.amount',
                 'loan_id', 'loan_id.amount')
    def _compute_total(self):
        for rec in self:
            rec.total_amount = round(sum(rec.expense_line_ids.mapped('amount')) or 0.0, 2)
            rec.loan_amount = rec.loan_id.amount or 0.0
            rec.balance = round(rec.total_amount - rec.loan_amount, 2)

    # === 状态机 ===

    def action_audit(self):
        """审核：待审核 → 已审核。有借款生成冲抵凭证（借 6401.xx / 贷 1221.01 + 差额补款/退款）；
        纯报销（无借款）生成两段式审核凭证（借 6401.xx / 贷 2241.06 应付员工）。"""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.expense_line_ids:
                raise ValidationError('报账单至少需要一条报销明细')
            if not rec.move_id:
                if rec.loan_id:
                    rec.move_id = rec._generate_settlement_move()
                else:
                    rec.move_id = rec._generate_reimbursement_move()
            rec.write({
                'state': 'audited',
                'auditor_id': self.env.user.id,
                'audit_date': fields.Datetime.now(),
            })

    def action_settle(self):
        """结算：已审核 → 已结算（有借款冲抵场景）；完全冲抵后借款单流转「已冲抵」。"""
        for rec in self:
            if rec.state != 'audited':
                continue
            if not rec.loan_id:
                raise ValidationError('纯报销（无借款）请走「出纳付款」完成结算，而非直接结算')
            rec.state = 'settled'
            if rec.loan_id.state == 'disbursed':
                rec.loan_id._mark_settled_if_clear()

    def action_pay(self):
        """出纳付款：已审核 → 已结算（纯报销两段式）；生成付款凭证 借 2241.06 / 贷 1002。"""
        for rec in self:
            if rec.state != 'audited':
                continue
            if rec.loan_id:
                raise ValidationError('有借款的报账请走「结算」完成冲抵，而非出纳付款')
            if not rec.payment_move_id:
                rec.payment_move_id = rec._generate_reimbursement_payment_move()
            rec.write({
                'state': 'settled',
                'payer_id': self.env.user.id,
                'pay_date': fields.Datetime.now(),
            })

    def _generate_reimbursement_move(self):
        """纯报销审核凭证 [BS-15 §3]：借 6401.xx 成本（按明细行分摊）/ 贷 2241.06 应付员工。"""
        self.ensure_one()
        total = self.total_amount or 0.0
        if total <= 0:
            raise ValidationError('报账总额为 0，无法生成报销凭证')

        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_EMPLOYEE)
        journal = self._tour_get_journal('general')
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self._tour_partner_id()
        labels = dict(self.env['tour.guide.expense.line']._fields['expense_type'].selection)

        lines = []
        for line in self.expense_line_ids:
            cost_acc = line.account_id or self._tour_get_account(
                self.GUIDE_EXPENSE_COST_MAP.get(line.expense_type,
                                                self.GUIDE_EXPENSE_COST_MAP['other']))
            lines.append({
                'account_id': cost_acc.id,
                'debit': line.amount,
                'analytic': analytic,
                'compliance_ref': 'cas1',
                'name': '报销-%s %s' % (labels.get(line.expense_type, ''),
                                      line.invoice_no or ''),
            })
        lines.append({
            'account_id': payable_acc.id,
            'partner_id': partner_id,
            'credit': total,
            'compliance_ref': 'pay_settle',
            'name': '应付员工报销 %s' % self.name,
        })

        move = self._tour_make_move(
            journal, self.report_date or fields.Date.context_today(self),
            self.name, lines, compliance_ref='cas1',
            narration='%s / 报销挂应付（待付款）' % (self.plan_code or '-'))
        move.action_post()
        return move.id

    def _generate_reimbursement_payment_move(self):
        """纯报销出纳付款凭证 [BS-15 §3]：借 2241.06 应付员工 / 贷 1002 银行存款。"""
        self.ensure_one()
        total = self.total_amount or 0.0
        if total <= 0:
            raise ValidationError('报账总额为 0，无法生成付款凭证')

        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_EMPLOYEE)
        bank_acc = self._tour_get_account(self.ACCOUNT_BANK)
        journal = self._tour_get_journal('bank')
        partner_id = self._tour_partner_id()

        lines = [{
            'account_id': payable_acc.id,
            'partner_id': partner_id,
            'debit': total,
            'compliance_ref': 'pay_settle',
            'name': '支付员工报销 %s' % self.name,
        }, {
            'account_id': bank_acc.id,
            'credit': total,
            'compliance_ref': 'pay_settle',
            'name': '付款 %s' % self.name,
        }]

        move = self._tour_make_move(
            journal, self.report_date or fields.Date.context_today(self),
            self.name, lines, compliance_ref='pay_settle',
            narration='%s / 报销付款' % (self.plan_code or '-'))
        move.action_post()
        return move.id

    def _generate_settlement_move(self):
        """报账冲抵凭证 [BS-06 §5.2]：
        借 6401.xx 成本 = 报账总额（按明细行分摊，挂 analytic）
        贷 1221.01 其他应收款—员工借款 = 借款金额（完全冲抵）
        差额：报账>借款 → 贷 1002（公司补款）；报账<借款 → 借 1002（员工退款）。
        """
        self.ensure_one()
        loan = self.loan_id
        total = self.total_amount or 0.0
        loan_amt = loan.amount or 0.0
        if total <= 0:
            raise ValidationError('报账总额为 0，无法生成冲抵凭证')

        loan_acc = self._tour_get_account(self.ACCOUNT_EMPLOYEE_LOAN)
        bank_acc = self._tour_get_account(self.ACCOUNT_BANK)
        journal = self._tour_get_journal('general')
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self._tour_partner_id()
        borrower = (self.employee_id.name if self.employee_id
                    else (self.guide_id.name if self.guide_id else '未关联员工'))
        narration = '%s / %s / 报账冲抵' % (self.plan_code or '-', borrower)
        labels = dict(self.env['tour.guide.expense.line']._fields['expense_type'].selection)

        lines = []
        # 借：成本（按明细行分摊到 6401.xx，挂 analytic，合规标注 cas1）
        for line in self.expense_line_ids:
            cost_acc = line.account_id or self._tour_get_account(
                self.GUIDE_EXPENSE_COST_MAP.get(line.expense_type,
                                                self.GUIDE_EXPENSE_COST_MAP['other']))
            lines.append({
                'account_id': cost_acc.id,
                'debit': line.amount,
                'analytic': analytic,
                'compliance_ref': 'cas1',
                'name': '报账-%s %s' % (labels.get(line.expense_type, ''),
                                      line.invoice_no or ''),
            })
        # 贷：冲抵借款 1221.01（完全冲抵）
        lines.append({
            'account_id': loan_acc.id,
            'partner_id': partner_id,
            'credit': loan_amt,
            'analytic': analytic,
            'compliance_ref': 'cas22_settle',
            'name': '冲抵员工借款 %s' % (loan.name or self.name),
        })
        # 差额补款/退款
        diff = round(total - loan_amt, 2)
        if diff > 0:
            lines.append({
                'account_id': bank_acc.id,
                'credit': diff,
                'compliance_ref': 'pay_settle',
                'name': '补款员工 %s' % self.name,
            })
        elif diff < 0:
            lines.append({
                'account_id': bank_acc.id,
                'debit': -diff,
                'compliance_ref': 'pay_settle',
                'name': '员工退款 %s' % self.name,
            })

        move = self._tour_make_move(
            journal, self.report_date or fields.Date.context_today(self),
            self.name, lines, compliance_ref='cas1', narration=narration)
        move.action_post()
        return move.id


class TourGuideExpenseLine(models.Model):
    _name = 'tour.guide.expense.line'
    _description = '导游报销明细行'
    _inherit = ['tour.accounting.mixin']

    EXPENSE_TYPE_SELECTION = [
        ('vehicle', '车费'),
        ('meal', '餐费'),
        ('ticket', '门票费'),
        ('hotel', '房费'),
        ('visa', '签证费'),
        ('guide', '导服费'),
        ('other', '其他'),
    ]

    # 差额征税可扣除成本性质集合（财税[2016]36号附件2：车/餐/门票/房/签证可扣除）[BS-15 §4]
    DEDUCTIBLE_EXPENSE_TYPES = ('vehicle', 'meal', 'ticket', 'hotel', 'visa')

    real_pay_id = fields.Many2one('tour.guide.real.pay', string='报账单',
                                  ondelete='cascade', required=True, index=True)
    expense_type = fields.Selection(EXPENSE_TYPE_SELECTION, string='成本类型',
                                    required=True, default='other')
    amount = fields.Float('金额', digits=(16, 2), required=True)
    supplier_id = fields.Many2one('res.partner', string='供应商')
    invoice_no = fields.Char('发票号')
    attachment = fields.Binary('票据附件')
    deductible = fields.Boolean(
        '差额征税可扣除', compute='_compute_deductible', store=True,
        help='可扣除 = 成本性质(车/餐/门票/房/签证) ∈ 可扣除集 AND 挂团进成本 AND 有发票号；'
             '员工自身差旅（不挂团）一律不可扣除 [财税2016-36号 / BS-15 §4.3]')
    account_id = fields.Many2one(
        'account.account', string='成本科目',
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost'))]",
        help='留空按成本类型默认映射 6401.1x')
    remark = fields.Text('备注')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 related='real_pay_id.company_id', store=True)

    @api.onchange('expense_type')
    def _onchange_expense_type(self):
        code = self.GUIDE_EXPENSE_COST_MAP.get(self.expense_type)
        if code and not self.account_id:
            self.account_id = self.env['account.account'].search(
                [('code', '=', code)], limit=1)
        # deductible 由 _compute_deductible 复合判断（性质 + 挂团 + 发票号）[BS-15 §4.3]

    @api.depends('expense_type', 'invoice_no', 'real_pay_id.plan_id')
    def _compute_deductible(self):
        """差额征税可扣除复合判断：成本性质 ∈ 可扣除集 AND 挂团进成本 AND 有发票号。"""
        for line in self:
            line.deductible = (
                line.expense_type in self.DEDUCTIBLE_EXPENSE_TYPES
                and bool(line.real_pay_id.plan_id)
                and bool(line.invoice_no)
            )

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('报销明细金额必须大于 0')

    @api.constrains('deductible', 'invoice_no')
    def _check_deductible_invoice(self):
        for rec in self:
            if rec.deductible and not rec.invoice_no:
                raise ValidationError('差额征税可扣除项目必须填写发票号')
