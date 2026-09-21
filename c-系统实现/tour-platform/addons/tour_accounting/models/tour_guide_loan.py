# -*- coding: utf-8 -*-
"""导游借款单 [TDS §2.2 / BS-06 §5.3-5.5 / BS-15 §2]。

链路：借款申请（待审批）→ 审批（已审批，借款人≠审批人）→ 放款（已放款，
    借 1221.01 其他应收款—员工借款 / 贷 1002 银行存款）→ 报账冲抵（已冲抵）。
内控校验：借款≠审批≠放款三方分离（R-27）、放款+30 天报账预警（R-29）、
    有未冲抵借款禁新借（R-30）。
"""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero


class TourGuideLoan(models.Model):
    _name = 'tour.guide.loan'
    _description = '导游借款单'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.accounting.mixin']
    _order = 'apply_date desc, id desc'

    # === 标识 ===
    name = fields.Char('借款单号', required=True, copy=False, default='新建',
                       help='自动流水，如 JK-000123')

    # === 业务关联 ===
    # 财务人事线：借款人维度挂 hr.employee；guide_id 保留为可空冗余（业务回溯/兼容旧单）
    employee_id = fields.Many2one('hr.employee', string='借款人（员工）', index=True,
                                  ondelete='restrict',
                                  default=lambda self: self.env.user.employee_id.id or False,
                                  help='借款/报销/佣金统一挂员工维度；凭证往来方取员工的工作联系人；'
                                       '员工自助默认取当前登录用户的员工档案')
    guide_id = fields.Many2one('tour.guide', string='导游', required=False,
                               index=True, ondelete='restrict')
    plan_id = fields.Many2one('tour.plan', string='团队', required=False,
                              index=True, ondelete='restrict',
                              help='挂团借款必填；员工备用金/差旅借款可不挂团')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)

    # === 借款信息 ===
    amount = fields.Monetary('借款金额', currency_field='currency_id',
                             required=True, help='>0，借款金额')
    purpose = fields.Text('借款用途')
    account_id = fields.Many2one(
        'account.account', string='放款账户',
        domain="[('account_type', '=', 'asset_cash')]",
        help='放款资金科目（贷方）；留空默认银行存款 1002')

    # === 状态机（待审批/已审批/已放款/已冲抵）===
    state = fields.Selection([
        ('draft', '待审批'),
        ('approved', '已审批'),
        ('disbursed', '已放款'),
        ('settled', '已冲抵'),
    ], string='状态', default='draft', required=True, index=True, tracking=True)

    # === 三方分离留痕（借款人≠审批人≠放款人）[BS-06 R-27] ===
    applicant_id = fields.Many2one('res.users', string='借款人',
                                   default=lambda self: self.env.user, required=True)
    approver_id = fields.Many2one('res.users', string='审批人')
    approve_date = fields.Datetime('审批时间')
    disburser_id = fields.Many2one('res.users', string='放款人')
    disbursement_date = fields.Datetime('放款时间')

    # === 时效（放款 + 30 天报账预警）[BS-06 R-29] ===
    apply_date = fields.Date('申请日期', default=fields.Date.context_today, required=True)
    loan_date = fields.Date('放款日期')
    due_date = fields.Date('报账截止日', help='= 放款日期 + 30 天')
    x_period_id = fields.Many2one(
        'tour.account.period', string='会计期间', index=True,
        compute='_compute_x_period_id', store=True, readonly=False,
        help='根据申请日期自动获取的会计期间')
    
    @api.depends('apply_date')
    def _compute_x_period_id(self):
        """根据申请日期自动计算会计期间"""
        for loan in self:
            if loan.apply_date:
                period = self.env['tour.account.period'].get_period_by_date(
                    loan.apply_date, loan.company_id)
                loan.x_period_id = period.id if period else False
            else:
                loan.x_period_id = False
    
    @api.constrains('apply_date', 'x_period_id')
    def _check_period_open(self):
        """检查会计期间是否开放"""
        for loan in self:
            if loan.apply_date and loan.x_period_id:
                if loan.x_period_id.state != 'open':
                    raise ValidationError(
                        f'会计期间 {loan.x_period_id.name} 已关闭，'
                        f'无法在 {loan.apply_date} 创建/修改借款单')
    is_overdue = fields.Boolean('已超期', compute='_compute_is_overdue', store=True,
                                help='已放款且超过报账截止日未冲抵')

    # === 会计凭证回链 ===
    move_id = fields.Many2one('account.move', string='放款凭证', copy=False,
                              ondelete='restrict', index=True)
    move_state = fields.Selection(related='move_id.state', string='凭证状态')

    # === 冲抵跟踪 ===
    x_expense_ids = fields.One2many('hr.expense', 'x_loan_id', string='报账费用')
    settled_amount = fields.Monetary('已冲抵金额', currency_field='currency_id',
                                     compute='_compute_settled', store=True)
    residual = fields.Monetary('未冲抵余额', currency_field='currency_id',
                               compute='_compute_settled', store=True,
                               help='= 借款金额 - 已冲抵金额')

    # === 归属 ===
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    # === Stat button counts ===
    expense_count = fields.Integer('报账费用数', compute='_compute_related_counts')
    move_count = fields.Integer('凭证数', compute='_compute_related_counts')

    @api.depends('move_id', 'x_expense_ids')
    def _compute_related_counts(self):
        for rec in self:
            rec.expense_count = len(rec.x_expense_ids) if rec.x_expense_ids else 0
            rec.move_count = 1 if rec.move_id else 0

    def action_view_expenses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '报账费用',
            'res_model': 'hr.expense',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.x_expense_ids.ids)],
        }

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            return {'type': 'ir.actions.act_window', 'name': '凭证', 'res_model': 'account.move', 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}
        return {
            'type': 'ir.actions.act_window',
            'name': '放款凭证',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    _uniq_loan_name = models.Constraint('unique(name)', '借款单号已存在')

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
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.guide.loan') or '新建'
            # 员工维度优先；未传时从导游反查
            employee_id = vals.get('employee_id')
            guide_id = vals.get('guide_id')
            if not employee_id and guide_id:
                guide = self.env['tour.guide'].browse(guide_id)
                if guide.employee_id:
                    employee_id = guide.employee_id.id
                    vals['employee_id'] = employee_id
            # R-30 未冲抵禁新借：有已放款未冲抵借款的员工不可再申请
            if employee_id:
                outstanding = self.search([
                    ('employee_id', '=', employee_id),
                    ('state', '=', 'disbursed'),
                ])
                if outstanding:
                    raise ValidationError(
                        '借款人存在未冲抵借款 %s，须先报账冲抵后方可申请新借款'
                        % outstanding[0].name)
        return super().create(vals_list)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('借款金额必须大于 0')

    @api.depends('x_expense_ids', 'x_expense_ids.state', 'x_expense_ids.total_amount_currency', 'state')
    def _compute_settled(self):
        for rec in self:
            settled_expenses = rec.x_expense_ids.filtered(
                lambda e: e.state in ('approved', 'posted', 'in_payment', 'paid'))
            settled = sum(settled_expenses.mapped('total_amount_currency'))
            rec.settled_amount = settled
            rec.residual = 0.0 if rec.state == 'settled' else round((rec.amount or 0.0) - settled, 2)

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(
                rec.state == 'disbursed' and rec.due_date and rec.due_date < today)

    # === 状态机 ===

    def action_approve(self):
        """审批：待审批 → 已审批；三方分离：审批人（当前用户）≠ 借款人。"""
        user = self.env.user
        for rec in self:
            if rec.state != 'draft':
                continue
            if rec.applicant_id and user.id == rec.applicant_id.id:
                raise ValidationError('不相容职务冲突：审批人「%s」不能是借款人' % user.name)
            rec.write({
                'state': 'approved',
                'approver_id': user.id,
                'approve_date': fields.Datetime.now(),
            })

    def action_disburse(self):
        """放款：已审批 → 已放款；生成放款凭证 借 1221.01 / 贷 1002；
        三方分离：放款人（当前用户）≠ 审批人 且 ≠ 借款人。"""
        user = self.env.user
        for rec in self:
            if rec.state != 'approved':
                continue
            if rec.approver_id and user.id == rec.approver_id.id:
                raise ValidationError('不相容职务冲突：放款人「%s」不能是审批人' % user.name)
            if rec.applicant_id and user.id == rec.applicant_id.id:
                raise ValidationError('不相容职务冲突：放款人「%s」不能是借款人' % user.name)
            today = fields.Date.context_today(self)
            if not rec.move_id:
                rec.move_id = rec._generate_disbursement_move(today)
            rec.write({
                'state': 'disbursed',
                'disburser_id': user.id,
                'disbursement_date': fields.Datetime.now(),
                'loan_date': today,
                'due_date': fields.Date.add(today, days=30),
            })

    def action_reject(self):
        """退回：待审批 → 草稿（复用 draft，撤销审批）。"""
        for rec in self:
            if rec.state not in ('draft', 'approved'):
                continue
            if rec.move_id:
                raise ValidationError('已放款借款不可退回')
            rec.state = 'draft'

    def _generate_disbursement_move(self, date):
        """放款凭证：借 1221.01 其他应收款—员工借款 / 贷 1002 银行存款。"""
        self.ensure_one()
        loan_acc = self._tour_get_account(self.ACCOUNT_EMPLOYEE_LOAN)
        fund_acc = self.account_id or self._tour_get_account(self.ACCOUNT_BANK)
        journal = self._tour_get_journal('bank')
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self._tour_partner_id()
        borrower = (self.employee_id.name if self.employee_id
                    else (self.guide_id.name if self.guide_id else '未关联员工'))
        narration = '%s / %s / 借款放款' % (self.plan_code or '-', borrower)

        lines = [{
            'account_id': loan_acc.id,
            'partner_id': partner_id,
            'debit': self.amount,
            'analytic': analytic,
            'compliance_ref': 'cas22',
            'name': '员工借款 %s' % self.name,
        }, {
            'account_id': fund_acc.id,
            'credit': self.amount,
            'compliance_ref': 'pay_settle',
            'name': '放款 %s' % self.name,
        }]

        move = self._tour_make_move(
            journal, date, self.name, lines,
            compliance_ref='cas22', narration=narration)
        move.action_post()
        return move.id

    def _mark_settled_if_clear(self):
        """报账结算后借款单流转为已冲抵（仅当 residual=0 即全额冲抵）。"""
        self.ensure_one()
        rounding = self.currency_id.rounding if self.currency_id else 0.01
        if self.state == 'disbursed' and float_is_zero(self.residual, precision_rounding=rounding):
            self.state = 'settled'

    @api.model
    def _cron_overdue_warning(self):
        """30 天报账预警：已放款且超过报账截止日未冲抵的借款，chatter 留痕预警。"""
        loans = self.search([
            ('state', '=', 'disbursed'),
            ('due_date', '<', fields.Date.context_today(self)),
        ])
        for loan in loans:
            borrower = (loan.employee_id.name if loan.employee_id
                        else (loan.guide_id.name or '-'))
            loan.message_post(
                body='⚠️ 借款 %s（%s）已超过报账截止日 %s，请尽快催办报账冲抵。'
                % (loan.name, borrower, loan.due_date))
        return loans.ids
