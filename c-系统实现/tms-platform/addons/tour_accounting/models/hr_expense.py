# -*- coding: utf-8 -*-
"""hr.expense 旅行社扩展 [BS-06 / BS-15]。

将导游报账功能迁移到标准 hr.expense 上：
- 每条费用明细 = 1 个 hr.expense 记录（取代旧 tour.guide.real.pay 1:N 结构）
- 费用类别用 product.product（含 x_expense_type）映射科目
- 有借款冲抵场景覆盖凭证生成（DR 6401.xx / CR 1221.01）
- 无借款走标准流程，payable 科目强制 2241.06
"""
from odoo import models, fields, api
from odoo.exceptions import UserError


DEDUCTIBLE_EXPENSE_TYPES = ('vehicle', 'meal', 'ticket', 'hotel', 'visa')


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    x_report_type = fields.Selection([
        ('expense', '费用报销'),
        ('income', '收入报账'),
    ], string='报账类型', default='expense', required=True,
       help='费用报销：员工垫付后公司还款；收入报账：员工代收款项上交公司')
    x_guide_id = fields.Many2one('tour.guide', string='导游', index=True,
                                 ondelete='restrict')
    x_plan_id = fields.Many2one('tour.plan', string='团队', index=True,
                                ondelete='restrict')
    x_plan_code = fields.Char('团号', related='x_plan_id.plan_code', store=True)
    x_loan_id = fields.Many2one(
        'tour.guide.loan', string='关联借款', index=True, ondelete='restrict',
        domain="[('employee_id', '=', employee_id), ('state', '=', 'disbursed')]",
        help='报账冲抵的借款单（须已放款）；留空为纯报销')
    x_invoice_no = fields.Char('发票号')
    x_deductible = fields.Boolean(
        '差额征税可扣除', compute='_compute_x_deductible', store=True,
        help='可扣除 = 成本性质(车/餐/门票/房/签证) ∈ 可扣除集 AND 挂团 AND 有发票号')

    @api.onchange('x_guide_id')
    def _onchange_x_guide_id(self):
        if self.x_guide_id and self.x_guide_id.employee_id:
            self.employee_id = self.x_guide_id.employee_id

    @api.onchange('employee_id')
    def _onchange_employee_for_guide(self):
        if self.employee_id and not self.x_guide_id:
            guide = self.env['tour.guide'].search(
                [('employee_id', '=', self.employee_id.id)], limit=1)
            if guide:
                self.x_guide_id = guide

    @api.depends('product_id', 'x_invoice_no', 'x_plan_id')
    def _compute_x_deductible(self):
        for rec in self:
            expense_type = (rec.product_id.x_expense_type
                            if rec.product_id and hasattr(rec.product_id, 'x_expense_type')
                            else False)
            rec.x_deductible = (
                expense_type in DEDUCTIBLE_EXPENSE_TYPES
                and bool(rec.x_plan_id)
                and bool(rec.x_invoice_no)
            )

    def _get_expense_account_destination(self):
        """纯报销（无借款）场景：payable 科目强制 2241.06（其他应付款—员工代付）。
        有借款冲抵场景不走此方法（_prepare_receipts_vals 已覆盖）。
        """
        if self.x_loan_id:
            return super()._get_expense_account_destination()
        acc = self.env['account.account'].search([('code', '=', '2241.06')], limit=1)
        if acc:
            return acc.id
        return super()._get_expense_account_destination()

    def _prepare_receipts_vals(self):
        """覆盖凭证生成：
        - 有借款冲抵时，贷方从 2241.06 改为 1221.01
        - 收入报账时，使用收入科目和应收科目
        """
        # 分离收入报账和费用报销
        income_expenses = self.filtered(lambda e: e.x_report_type == 'income')
        expense_expenses = self.filtered(lambda e: e.x_report_type != 'income')

        return_vals = []

        # 费用报销（标准流程）
        if expense_expenses:
            has_loan = expense_expenses.filtered('x_loan_id')
            no_loan = expense_expenses - has_loan
            if no_loan:
                return_vals.extend(super(HrExpense, no_loan)._prepare_receipts_vals())
            if has_loan:
                return_vals.extend(has_loan._prepare_loan_offset_receipts_vals())

        # 收入报账（反向流程）
        if income_expenses:
            return_vals.extend(income_expenses._prepare_income_receipts_vals())

        return return_vals

    def _prepare_income_receipts_vals(self):
        """收入报账凭证：DR 1221.xx（应收）/ CR 收入科目。"""
        return_vals = []
        for employee_sudo, expenses_sudo in self.sudo().grouped('employee_id').items():
            # 应收科目：1221.xx（其他应收款—员工）
            receivable_acc = self.env['account.account'].search(
                [('code', '=like', '1221%')], limit=1)
            if not receivable_acc:
                raise UserError('未找到科目 1221.xx（其他应收款—员工）')

            partner = employee_sudo.work_contact_id

            line_ids = []
            total = 0.0
            for expense in expenses_sudo:
                # 收入科目：使用产品的收入科目或默认主营业务收入
                income_account = expense._get_income_account()
                line_ids.append((0, 0, {
                    'name': expense._get_move_line_name(),
                    'account_id': income_account.id,
                    'quantity': expense.quantity or 1,
                    'price_unit': expense.price_unit,
                    'product_id': expense.product_id.id,
                    'product_uom_id': expense.product_uom_id.id,
                    'analytic_distribution': expense.analytic_distribution,
                    'expense_id': expense.id,
                    'partner_id': partner.id if partner else False,
                    'tax_ids': [(6, 0, expense.tax_ids.ids)],
                    'credit': expense.total_amount,
                    'debit': 0.0,
                }))
                total += expense.total_amount

            # 借方：应收科目
            line_ids.append((0, 0, {
                'name': '员工收入报账',
                'account_id': receivable_acc.id,
                'quantity': 1,
                'price_unit': total,
                'partner_id': partner.id if partner else False,
                'expense_id': expenses_sudo[0].id,
                'debit': total,
                'credit': 0.0,
            }))

            journal = (
                expenses_sudo[0].company_id.expense_journal_id
                or self.env['account.journal'].search(
                    [('company_id', '=', expenses_sudo[0].company_id.id),
                     ('type', '=', 'purchase')], limit=1)
            )

            return_vals.append({
                'name': '/',
                'expense_ids': [(6, 0, expenses_sudo.ids)],
                'ref': expenses_sudo[0].name if len(expenses_sudo) == 1 else '收入报账',
                'move_type': 'out_invoice',  # 收入报账用销售发票类型（应收）
                'partner_id': partner.id if partner else False,
                'commercial_partner_id': employee_sudo.user_partner_id.id,
                'currency_id': expenses_sudo.company_currency_id.id,
                'company_id': expenses_sudo.company_id.id,
                'journal_id': journal.id if journal else False,
                'line_ids': line_ids,
                'partner_bank_id': employee_sudo.primary_bank_account_id.id,
            })
        return return_vals

    def _get_income_account(self):
        """获取收入科目：优先使用产品的收入科目，否则用主营业务收入。"""
        self.ensure_one()
        # 尝试从产品获取收入科目
        if self.product_id and hasattr(self.product_id, 'property_account_income_id'):
            if self.product_id.property_account_income_id:
                return self.product_id.property_account_income_id
        # 默认主营业务收入 6001.01
        acc = self.env['account.account'].search([('code', '=like', '6001%')], limit=1)
        if acc:
            return acc
        # 如果找不到，用费用科目的对方科目
        return self._get_base_account()

    def _prepare_loan_offset_receipts_vals(self):
        """有借款冲抵凭证：DR 6401.xx / CR 1221.01（全额冲抵借款）。"""
        self.ensure_one() if len(self) == 1 else None
        return_vals = []
        for employee_sudo, expenses_sudo in self.sudo().grouped('employee_id').items():
            loan_acc = self.env['account.account'].search(
                [('code', '=', '1221.01')], limit=1)
            if not loan_acc:
                raise UserError('未找到科目 1221.01（其他应收款—员工借款）')

            partner = employee_sudo.work_contact_id

            line_ids = []
            total = 0.0
            for expense in expenses_sudo:
                account = expense._get_base_account()
                line_ids.append((0, 0, {
                    'name': expense._get_move_line_name(),
                    'account_id': account.id,
                    'quantity': expense.quantity or 1,
                    'price_unit': expense.price_unit,
                    'product_id': expense.product_id.id,
                    'product_uom_id': expense.product_uom_id.id,
                    'analytic_distribution': expense.analytic_distribution,
                    'expense_id': expense.id,
                    'partner_id': partner.id if partner else False,
                    'tax_ids': [(6, 0, expense.tax_ids.ids)],
                }))
                total += expense.total_amount

            loan_amount = sum(exp.x_loan_id.amount for exp in expenses_sudo if exp.x_loan_id)
            line_ids.append((0, 0, {
                'name': '冲抵借款',
                'account_id': loan_acc.id,
                'quantity': 1,
                'price_unit': -total,
                'partner_id': partner.id if partner else False,
                'expense_id': expenses_sudo[0].id,
            }))

            journal = (
                expenses_sudo[0].company_id.expense_journal_id
                or self.env['account.journal'].search(
                    [('company_id', '=', expenses_sudo[0].company_id.id),
                     ('type', '=', 'purchase')], limit=1)
            )

            return_vals.append({
                'name': '/',
                'expense_ids': [(6, 0, expenses_sudo.ids)],
                'ref': expenses_sudo[0].name if len(expenses_sudo) == 1 else '导游报账冲抵借款',
                'move_type': 'in_receipt',
                'partner_id': partner.id if partner else False,
                'commercial_partner_id': employee_sudo.user_partner_id.id,
                'currency_id': expenses_sudo.company_currency_id.id,
                'company_id': expenses_sudo.company_id.id,
                'journal_id': journal.id if journal else False,
                'line_ids': line_ids,
                'partner_bank_id': employee_sudo.primary_bank_account_id.id,
            })
        return return_vals

    def _mark_loan_settled(self):
        """报账审核后，检查关联借款是否已全额冲抵，是则流转借款状态为已冲抵。"""
        for expense in self:
            if expense.x_loan_id and expense.x_loan_id.state == 'disbursed':
                expense.x_loan_id._mark_settled_if_clear()

    def _do_approve(self, check=True):
        """实际审批完成后触发借款冲抵状态检查。"""
        res = super()._do_approve(check=check)
        self._mark_loan_settled()
        return res
