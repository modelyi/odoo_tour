# -*- coding: utf-8 -*-
"""导游报账单 + 报销明细行 [TDS §2.2 / BS-06 §5.2/§5.4]。

链路：报账提交（待审核）→ 报账审核（已审核，生成冲抵凭证
    借 6401.xx 成本 / 贷 1221.01 冲抵借款，差额补款/退款）→ 已结算
    （完全冲抵后借款单流转「已冲抵」）。
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
    guide_id = fields.Many2one('tour.guide', string='导游', required=True,
                               index=True, ondelete='restrict')
    plan_id = fields.Many2one('tour.plan', string='团队', required=True,
                              index=True, ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    loan_id = fields.Many2one(
        'tour.guide.loan', string='关联借款单', index=True, ondelete='restrict',
        domain="[('guide_id', '=', guide_id), ('state', '=', 'disbursed')]",
        help='报账冲抵的借款单（须已放款）')

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

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    _uniq_real_pay_name = models.Constraint('unique(name)', '报账单号已存在')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.guide.real.pay') or '新建'
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
        """审核：待审核 → 已审核；生成冲抵凭证（借 6401.xx / 贷 1221.01 + 差额补款/退款）。"""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.expense_line_ids:
                raise ValidationError('报账单至少需要一条报销明细')
            if not rec.loan_id:
                raise ValidationError('报账冲抵必须关联借款单')
            if not rec.move_id:
                rec.move_id = rec._generate_settlement_move()
            rec.write({
                'state': 'audited',
                'auditor_id': self.env.user.id,
                'audit_date': fields.Datetime.now(),
            })

    def action_settle(self):
        """结算：已审核 → 已结算；完全冲抵后借款单流转「已冲抵」。"""
        for rec in self:
            if rec.state != 'audited':
                continue
            rec.state = 'settled'
            if rec.loan_id and rec.loan_id.state == 'disbursed':
                rec.loan_id._mark_settled_if_clear()

    def _generate_settlement_move(self):
        """报账冲抵凭证 [BS-06 §5.2]：
        借 6401.xx 成本 = 报账总额（按明细行分摊，挂 analytic）
        贷 1221.01 其他应收款—导游借款 = 借款金额（完全冲抵）
        差额：报账>借款 → 贷 1002（公司补款）；报账<借款 → 借 1002（导游退款）。
        """
        self.ensure_one()
        loan = self.loan_id
        total = self.total_amount or 0.0
        loan_amt = loan.amount or 0.0
        if total <= 0:
            raise ValidationError('报账总额为 0，无法生成冲抵凭证')

        loan_acc = self._tour_get_account(self.ACCOUNT_GUIDE_LOAN)
        bank_acc = self._tour_get_account(self.ACCOUNT_BANK)
        journal = self._tour_get_journal('general')
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self.guide_id.partner_id.id if self.guide_id.partner_id else None
        narration = '%s / %s / 报账冲抵' % (
            self.plan_code or '-', self.guide_id.name if self.guide_id else '未关联导游')
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
            'name': '冲抵导游借款 %s' % (loan.name or self.name),
        })
        # 差额补款/退款
        diff = round(total - loan_amt, 2)
        if diff > 0:
            lines.append({
                'account_id': bank_acc.id,
                'credit': diff,
                'compliance_ref': 'pay_settle',
                'name': '补款导游 %s' % self.name,
            })
        elif diff < 0:
            lines.append({
                'account_id': bank_acc.id,
                'debit': -diff,
                'compliance_ref': 'pay_settle',
                'name': '导游退款 %s' % self.name,
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
        ('guide', '导服费'),
        ('other', '其他'),
    ]

    real_pay_id = fields.Many2one('tour.guide.real.pay', string='报账单',
                                  ondelete='cascade', required=True, index=True)
    expense_type = fields.Selection(EXPENSE_TYPE_SELECTION, string='成本类型',
                                    required=True, default='other')
    amount = fields.Float('金额', digits=(16, 2), required=True)
    supplier_id = fields.Many2one('res.partner', string='供应商')
    invoice_no = fields.Char('发票号')
    attachment = fields.Binary('票据附件')
    deductible = fields.Boolean(
        '差额征税可扣除', default=False,
        help='可扣除项（车/餐/门票/房）必须取得合规发票 [财税2016-36号]')
    account_id = fields.Many2one(
        'account.account', string='成本科目',
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost'))]",
        help='留空按成本类型默认映射 6401.xx')
    remark = fields.Text('备注')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 related='real_pay_id.company_id', store=True)

    @api.onchange('expense_type')
    def _onchange_expense_type(self):
        code = self.GUIDE_EXPENSE_COST_MAP.get(self.expense_type)
        if code and not self.account_id:
            self.account_id = self.env['account.account'].search(
                [('code', '=', code)], limit=1)
        # 差额征税可扣除项：车/餐/门票/房；导服/其他 不可扣除 [BS-10 §4.6]
        self.deductible = self.expense_type in ('vehicle', 'meal', 'ticket', 'hotel')

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
