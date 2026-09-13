# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourReconciliation(models.Model):
    _name = 'tour.reconciliation'
    _description = '对账'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.accounting.mixin']
    _order = 'id desc'

    name = fields.Char('对账单号', required=True, copy=False, default='新建')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.reconciliation') or '新建'
        return super().create(vals_list)

    verify_type = fields.Selection([
        ('group_tour', '团款对账'),
        ('ditch', '地接对账'),
        ('vehicle', '车费对账'),
        ('ticket', '票务对账'),
        ('insurance', '保险对账'),
        ('meal', '餐费对账'),
        ('hotel', '房费对账'),
        ('scenic', '门票对账'),
        ('visa', '签证对账'),
        ('self_fee', '自费对账'),
        ('shop', '购物对账'),
        ('refund', '团款退款对账'),
        ('delegate', '代收对账'),
    ], string='对账类型', required=True, index=True,
       help='11 类往来对账 + 团款退款/代收两项（BS-07）')

    supplier_id = fields.Many2one('res.partner', string='对方单位', index=True)
    supplier_name = fields.Char('对方单位名称')
    period_begin = fields.Date('对账期间开始')
    period_end = fields.Date('对账期间结束')

    # === 金额（Phase 2：由 account.move.line 未核销项派生，不再手工维护）[TDS §4.5] ===
    total_amount = fields.Float('应收/应付总额', digits=(16, 2),
                                compute='_compute_amounts',
                                help='= Σ 该往来方期间内往来科目凭证行 balance')
    settled_amount = fields.Float('已收/已付总额', digits=(16, 2),
                                  compute='_compute_amounts',
                                  help='= 总额 - 未核销（已核销部分）')
    unsettled_amount = fields.Float('未收/未付总额', digits=(16, 2),
                                    compute='_compute_amounts',
                                    help='= Σ 该往来方未核销凭证行 amount_residual')
    invoice_collected = fields.Float('已收集发票金额', digits=(16, 2),
                                     help='应付类对账的合规发票归集 [财税2016-36号]')
    invoice_gap = fields.Float('发票缺口', digits=(16, 2), compute='_compute_invoice_gap',
                               help='= 已收/已付 - 已收集发票')
    aging_days = fields.Integer('最大账龄天数', help='应收账款账龄分析 [CAS 8-减值]')

    # === 差异调整（业务对账差异经 account.move 落地）[BS-10 §7.7 / TDS §4.5] ===
    adjust_amount = fields.Float('差异调整金额', digits=(16, 2),
                                 help='核对确认的差异，正数=调增应收/收入，负数=调减；确认后生成调整凭证')
    diff_move_id = fields.Many2one('account.move', string='差异调整凭证', copy=False,
                                   ondelete='restrict', index=True)
    diff_move_state = fields.Selection(related='diff_move_id.state', string='调整凭证状态')

    state = fields.Selection([
        ('pending', '待对账'),
        ('verified', '已对账'),
        ('settled', '已结清'),
    ], string='状态', default='pending', required=True, index=True)

    verify_user_id = fields.Many2one('res.users', string='对账人')
    verify_date = fields.Date('对账日期')
    confirm_user_id = fields.Many2one('res.users', string='确认人')
    confirm_date = fields.Date('确认日期')
    remark = fields.Text('备注')

    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    line_ids = fields.One2many('tour.reconciliation.line', 'reconciliation_id',
                               string='对账明细行')

    def _reconciliation_move_lines(self):
        """该对账单（往来方 + 期间 + 往来科目）的已过账凭证行。"""
        self.ensure_one()
        if not self.supplier_id:
            return self.env['account.move.line']
        return self._partner_move_lines(
            self.supplier_id.id,
            account_ids=self._tour_reconcile_account_ids(),
            date_from=self.period_begin, date_to=self.period_end)

    @api.depends('supplier_id', 'period_begin', 'period_end')
    def _compute_amounts(self):
        for rec in self:
            lines = rec._reconciliation_move_lines()
            total = sum(lines.mapped('balance')) if lines else 0.0
            unsettled = sum(lines.mapped('amount_residual')) if lines else 0.0
            rec.total_amount = total
            rec.unsettled_amount = unsettled
            rec.settled_amount = total - unsettled

    @api.depends('settled_amount', 'invoice_collected')
    def _compute_invoice_gap(self):
        for rec in self:
            rec.invoice_gap = (rec.settled_amount or 0.0) - (rec.invoice_collected or 0.0)

    @api.constrains('verify_user_id', 'confirm_user_id')
    def _check_separation(self):
        """对账人 ≠ 确认人（内控-职务分离）"""
        for rec in self:
            if rec.verify_user_id and rec.confirm_user_id \
                    and rec.verify_user_id == rec.confirm_user_id:
                raise ValidationError('对账人与确认人不能是同一人（不相容职务分离）')

    def action_verify(self):
        for rec in self:
            if rec.state != 'pending':
                raise ValidationError('仅「待对账」可核对')
            if not rec.verify_user_id:
                rec.verify_user_id = self.env.user
            rec.verify_date = fields.Date.context_today(self)
            rec.state = 'verified'

    def action_settle(self):
        for rec in self:
            if rec.state != 'verified':
                raise ValidationError('仅「已对账」可结清')
            if not rec.confirm_user_id:
                rec.confirm_user_id = self.env.user
            rec.confirm_date = fields.Date.context_today(self)
            rec.state = 'settled'

    def action_post_diff(self):
        """把核对确认的差异金额落到 account.move（幂等，diff_move_id 判断）。"""
        for rec in self:
            if rec.diff_move_id:
                continue
            if not rec.adjust_amount:
                raise ValidationError('请先填写差异调整金额')
            rec.diff_move_id = rec._generate_diff_move()

    def _generate_diff_move(self):
        """差异调整凭证 [BS-10 §7.7.1]：
        adjust_amount > 0：借 1122.01 应收团款 / 贷 6001.01 主营收入
        adjust_amount < 0：反向（借 6001.01 / 贷 1122.01 应收团款）
        """
        self.ensure_one()
        amount = abs(self.adjust_amount)
        receivable = self._tour_get_account(self.ACCOUNT_RECEIVABLE_TOUR)
        revenue = self._tour_get_account(self.ACCOUNT_REVENUE_GROSS)
        journal = self._tour_get_journal('general')
        partner_id = self.supplier_id.id
        narration = '%s / %s / 对账差异调整' % (
            self.name, self.supplier_id.name if self.supplier_id else '-')

        if self.adjust_amount > 0:
            lines = [
                {'account_id': receivable.id, 'partner_id': partner_id,
                 'debit': amount, 'compliance_ref': 'cas22', 'name': '对账差异调增应收 %s' % self.name},
                {'account_id': revenue.id, 'credit': amount,
                 'compliance_ref': 'cas14', 'name': '对账差异调增收入 %s' % self.name},
            ]
        else:
            lines = [
                {'account_id': revenue.id, 'debit': amount,
                 'compliance_ref': 'cas14', 'name': '对账差异调减收入 %s' % self.name},
                {'account_id': receivable.id, 'partner_id': partner_id,
                 'credit': amount, 'compliance_ref': 'cas22', 'name': '对账差异调减应收 %s' % self.name},
            ]

        move = self._tour_make_move(
            journal, fields.Date.context_today(self), self.name, lines,
            compliance_ref='cas14', narration=narration)
        move.action_post()
        return move.id


class TourReconciliationLine(models.Model):
    _name = 'tour.reconciliation.line'
    _description = '对账明细行'
    _inherit = ['tour.accounting.mixin']
    _order = 'id'

    reconciliation_id = fields.Many2one('tour.reconciliation', string='对账单',
                                        required=True, ondelete='cascade', index=True)
    plan_id = fields.Many2one('tour.plan', string='团队订单', index=True)
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    begin_date = fields.Date('出团日期', related='plan_id.begin_date', store=True)
    guest_count = fields.Integer('客人数', related='plan_id.guest_count', store=True)

    # === 金额（Phase 2：由该团 + 该往来方的 account.move.line 派生）[TDS §4.5] ===
    amount = fields.Float('应收/应付金额', digits=(16, 2), compute='_compute_amounts',
                          help='= Σ 该团该往来方往来科目凭证行 balance')
    settled_amount = fields.Float('已收/已付金额', digits=(16, 2), compute='_compute_amounts')
    unsettled_amount = fields.Float('未收/未付金额', digits=(16, 2), compute='_compute_amounts',
                                    help='= Σ 该团该往来方未核销 amount_residual')
    invoice_amount = fields.Float('已取得发票金额', digits=(16, 2))

    verify_state = fields.Selection([
        ('unverified', '未核对'),
        ('verified', '已核对'),
        ('diff', '有差异'),
    ], string='核对状态', default='unverified', required=True)
    diff_reason = fields.Text('差异原因')
    remark = fields.Text('备注')

    @api.depends('plan_id', 'reconciliation_id.supplier_id',
                 'reconciliation_id.period_begin', 'reconciliation_id.period_end')
    def _compute_amounts(self):
        for line in self:
            rec = line.reconciliation_id
            analytic = line.plan_id.analytic_account_id if line.plan_id else False
            if not rec or not rec.supplier_id:
                line.amount = line.settled_amount = line.unsettled_amount = 0.0
                continue
            lines = self._partner_move_lines(
                rec.supplier_id.id,
                account_ids=self._tour_reconcile_account_ids(),
                date_from=rec.period_begin, date_to=rec.period_end,
                analytic_account_id=analytic.id if analytic else None)
            total = sum(lines.mapped('balance')) if lines else 0.0
            unsettled = sum(lines.mapped('amount_residual')) if lines else 0.0
            line.amount = total
            line.unsettled_amount = unsettled
            line.settled_amount = total - unsettled

    @api.constrains('verify_state', 'diff_reason')
    def _check_diff_reason(self):
        for rec in self:
            if rec.verify_state == 'diff' and not rec.diff_reason:
                raise ValidationError('核对状态为「有差异」时必须填写差异原因')
