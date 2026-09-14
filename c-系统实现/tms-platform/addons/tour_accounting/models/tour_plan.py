# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourPlan(models.Model):
    _name = 'tour.plan'
    _inherit = ['tour.plan', 'tour.accounting.mixin']

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='分析账户', copy=False, index=True,
        help='一团一核算：团号即分析账户名，确认时自动创建 [BS-10 §六]')

    # === 收入确认凭证回链 [Phase 2] ===
    income_move_id = fields.Many2one(
        'account.move', string='收入确认凭证', copy=False, ondelete='restrict',
        index=True, help='出团/完成时确认收入生成的凭证（拆税：借预收/贷收入不含税/贷销项税）[BS-11 §7.1]')
    income_move_state = fields.Selection(related='income_move_id.state', string='收入凭证状态')

    # === 差额征税抵减凭证回链 [Phase 3] ===
    vat_deduct_move_id = fields.Many2one(
        'account.move', string='差额抵减凭证', copy=False, ondelete='restrict',
        index=True, help='差额征税销项税额抵减凭证（借 2221.03/2221.07 / 贷成本）[BS-11 §7.2.2]')
    vat_deduct_move_state = fields.Selection(related='vat_deduct_move_id.state', string='抵减凭证状态')

    # === 成本侧 P2P 回链 [TDS §2.3] ===
    cost_bill_id = fields.Many2one(
        'account.move', string='成本应付账单', copy=False, ondelete='restrict',
        index=True, help='P2P：out_sum 生成的供应商应付账单 vendor bill（借 6401 / 贷 2202）')
    cost_bill_state = fields.Selection(related='cost_bill_id.state', string='成本账单状态')

    # === 开票进度跟踪 [BS-12 §4.3 / §8.3] ===
    invoice_ids = fields.Many2many(
        'account.move', 'tour_invoice_plan_rel', 'plan_id', 'move_id',
        string='关联发票', domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]")
    invoice_amount_total = fields.Float(
        '发票已开票金额', digits=(16, 2), compute='_compute_invoice_progress',
        help='= Σ 已开票 out_invoice 含税金额')
    invoice_progress = fields.Float(
        '开票进度(%)', digits=(16, 2), compute='_compute_invoice_progress',
        help='= invoice_money ÷ (invoice_money + un_invoice_money)')

    @api.depends('invoice_ids', 'invoice_ids.move_type', 'invoice_ids.state',
                 'invoice_money', 'un_invoice_money')
    def _compute_invoice_progress(self):
        for rec in self:
            rec.invoice_amount_total = sum(rec.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice').mapped('amount_total_signed'))
            total = (rec.invoice_money or 0.0) + (rec.un_invoice_money or 0.0)
            rec.invoice_progress = (
                (rec.invoice_money or 0.0) / total * 100.0) if total else 0.0

    # === Smart Button 计数（发票/收款/核算）[界面改造样板] ===
    # 反向 One2many：收款认领/核算台账按 plan_id 挂到团
    claim_ids = fields.One2many('tour.payment.claim', 'plan_id', string='收款认领')
    account_ids = fields.One2many('tour.plan.account', 'plan_id', string='核算台账')
    invoice_count = fields.Integer('发票数', compute='_compute_invoice_count')
    claim_count = fields.Integer('收款数', compute='_compute_claim_count')
    account_count = fields.Integer('核算数', compute='_compute_account_count')

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    @api.depends('claim_ids')
    def _compute_claim_count(self):
        for rec in self:
            rec.claim_count = len(rec.claim_ids)

    @api.depends('account_ids')
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = len(rec.account_ids)

    def action_view_invoices(self):
        """Smart button：跳转到该团的发票（out_invoice/out_refund）。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '发票',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                '|', ('tour_plan_id', '=', self.id),
                ('id', 'in', self.invoice_ids.ids),
            ],
            'context': {'default_move_type': 'out_invoice'},
        }

    def action_view_claims(self):
        """Smart button：跳转到该团的收款认领列表。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '收款认领',
            'res_model': 'tour.payment.claim',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    def action_view_account(self):
        """Smart button：跳转到该团的单团核算台账（1:1）。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '单团核算',
            'res_model': 'tour.plan.account',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    def action_confirm(self):
        """草稿 → 待确认 → 已确认；进入 confirmed 时自动创建分析账户 + 核算台账。"""
        res = super().action_confirm()
        for rec in self:
            if rec.state == 'confirmed':
                rec._ensure_analytic_account()
                rec._ensure_plan_account()
        return res

    def _ensure_analytic_account(self):
        """确保团队有 1:1 的分析账户（幂等），命名「团号-团名」。"""
        self.ensure_one()
        if self.analytic_account_id:
            return self.analytic_account_id
        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            plan = self.env['account.analytic.plan'].search(
                [('name', 'ilike', 'project')], limit=1)
        analytic = self.env['account.analytic.account'].create({
            'name': '%s-%s' % (self.plan_code or 'PLAN', self.plan_name or ''),
            'plan_id': plan.id,
            'tour_plan_id': self.id,
            'company_id': self.company_id.id,
        })
        self.analytic_account_id = analytic.id
        return analytic

    def _ensure_plan_account(self):
        """确保团队有 1:1 的核算台账 tour.plan.account（幂等）[Phase 2]。"""
        self.ensure_one()
        if not self.analytic_account_id:
            self._ensure_analytic_account()
        existing = self.env['tour.plan.account'].search(
            [('plan_id', '=', self.id)], limit=1)
        if existing:
            return existing
        return self.env['tour.plan.account'].create({
            'plan_id': self.id,
            'company_id': self.company_id.id,
            'department_id': self.department_id.id,
        })

    # === 收入确认（预收 → 收入，Phase 2 无税版）[BS-10 §7.2 / TDS §5.3] ===

    def _revenue_amount(self):
        """收入确认金额 [BS-14 §5.2]：
        - 总额法（组团 1/12/13/14/15/21/31）：全额收入报价 in_com_quo_sum（含税），
          不再用 _plan_prepay_balance 残值兜底（避免只记已收款部分）[BS-14 §5.2.2]
        - 净额法（代订 41）：差价 = in_sum - out_sum
        Phase 2 无税；差额征税销项税留 Phase 3。
        """
        self.ensure_one()
        if self.biz_mode in self.REVENUE_GROSS_MODES:
            return self.in_com_quo_sum or 0.0
        return (self.in_sum or 0.0) - (self.out_sum or 0.0)

    def _revenue_account_and_compliance(self):
        self.ensure_one()
        if self.biz_mode in self.REVENUE_GROSS_MODES:
            return self._tour_get_account(self.ACCOUNT_REVENUE_GROSS), 'cas14_principal'
        if self.biz_mode in self.REVENUE_DD_MODES:
            return self._tour_get_account(self.ACCOUNT_REVENUE_NET_DD), 'cas14_agent'
        return self._tour_get_account(self.ACCOUNT_REVENUE_NET_DT), 'cas14_agent'

    def _existing_revenue_move(self):
        """该团已在账上的收入确认凭证（posted entry，含 6001.0x 收入行 + 团分析账户）。

        防重复确认收入：批量过账/脚本重跑时，即便 income_move_id 未回链，
        也能识别出账上已有收入凭证，避免二次确认（幂等兜底）[P0-2]。
        """
        self.ensure_one()
        if not self.analytic_account_id:
            return self.env['account.move']
        lines = self.env['account.analytic.line'].search([
            ('account_id', '=', self.analytic_account_id.id),
            ('move_line_id', '!=', False),
        ])
        for move in lines.mapped('move_line_id.move_id'):
            if move.state != 'posted' or move.move_type != 'entry':
                continue
            if any(l.account_id.account_type in ('income', 'income_other')
                   for l in move.line_ids):
                return move
        return self.env['account.move']

    def action_recognize_revenue(self):
        """确认收入（幂等，income_move_id 判断）——借预收 / 贷主营收入，无税。"""
        for rec in self:
            if rec.income_move_id:
                continue
            existing = rec._existing_revenue_move()
            if existing:
                rec.income_move_id = existing.id
                continue
            rec.income_move_id = rec._generate_revenue_move()

    def _generate_revenue_move(self):
        """生成收入确认凭证 [BS-10 §7.2 / BS-11 §7.1]：拆税。

        总额法（DTO/DSO）：借 2203.01 预收(含税 G) / 贷 6001.0x 收入(不含税 G÷(1+r)) / 贷 销项税(G×r÷(1+r))
        净额法（其余）：借 2203.01 预收(差价含税) / 贷 6001.0x 收入(不含税) / 贷 销项税
        金额字段一律含税口径，价税分离后分别入账 [BS-11 §五]。
        """
        self.ensure_one()
        amount = self._revenue_amount()
        if amount <= 0:
            raise ValidationError(
                '团队 %s 无可确认收入金额（预收/差价为 0 或负），'
                '请先完成收款或检查收入/成本数据' % (self.plan_code or ''))

        revenue_acc, compliance = self._revenue_account_and_compliance()
        _taxpayer_type, rate_pct, _enabled = self._tour_vat_params()
        r = rate_pct / 100.0
        # 价税分离：不含税收入四舍五入，销项税 = 余额，保证借贷平衡 [BS-11 §4]
        net_revenue = round(amount / (1 + r), 2) if r else amount
        tax = round(amount - net_revenue, 2)
        tax_acc = self._tour_vat_account()

        prepay_acc = self.env['account.account'].search(
            [('code', '=', self.ACCOUNT_PREPAY_TOUR)], limit=1)
        if not prepay_acc:
            prepay_acc = self._tour_get_account(self.ACCOUNT_PREPAY)

        analytic = self._plan_analytic_distribution(self)
        partner_id = self.supplier_id.id if self.supplier_id else None
        narration = '%s / %s / 收入确认' % (
            self.plan_code or '-', self.supplier_id.name if self.supplier_id else '未关联客户')

        lines = [{
            'account_id': prepay_acc.id,
            'partner_id': partner_id,
            'debit': amount,
            'analytic': analytic,
            'name': '结转预收 %s' % (self.plan_code or ''),
        }, {
            'account_id': revenue_acc.id,
            'credit': net_revenue,
            'analytic': analytic,
            'name': '确认收入(不含税) %s' % (self.plan_code or ''),
        }]
        if tax > 0:
            lines.append({
                'account_id': tax_acc.id,
                'credit': tax,
                'analytic': analytic,
                'compliance_ref': 'vat_reg',
                'name': '销项税额 %s' % (self.plan_code or ''),
            })

        move = self._tour_make_move(
            self._tour_get_journal('sale'),
            self.end_date or fields.Date.context_today(self),
            self.plan_code, lines,
            compliance_ref=compliance, narration=narration)
        move.action_post()
        return move.id

    # === 差额征税销项税额抵减 [BS-11 §7.2.2 / §8] ===

    def _vat_deductible_base(self):
        """可扣除成本抵减基数 D' = max(0, D − 无票可扣除额) [BS-11 §8.3]。"""
        self.ensure_one()
        deductible, _ = self._plan_cost_vat_split(self)
        gap = self.un_invoice_money or 0.0
        return max(0.0, deductible - gap)

    def action_generate_vat_deduction(self):
        """生成差额征税抵减凭证（幂等，vat_deduct_move_id 判断）。"""
        for rec in self:
            if rec.vat_deduct_move_id:
                continue
            rec.vat_deduct_move_id = rec._generate_vat_deduction_move()

    def _generate_vat_deduction_move(self):
        """生成差额征税销项税额抵减凭证 [BS-11 §7.2.2]：
        借 2221.03(一般)/2221.07(小规模) = 抵减额 = D'÷(1+r)×r
        贷 6401.0N 成本—对应分项 = 同额（按可扣除科目分摊）
        仅总额法 + 差额征税启用 + tour_vat_deductible 科目有发生额时触发。
        """
        self.ensure_one()
        _taxpayer_type, rate_pct, enabled = self._tour_vat_params()
        if not enabled:
            raise ValidationError('公司未启用差额征税（tour_diff_tax_enabled），无法生成抵减凭证')
        if self.biz_mode not in self.REVENUE_GROSS_MODES:
            raise ValidationError('差额征税仅适用于总额法（组团 DTO/DSO），净额法无差额扣除环节')
        r = rate_pct / 100.0
        base = self._vat_deductible_base()
        if base <= 0:
            raise ValidationError('该团无可扣除成本（有票口径），无法生成抵减凭证')
        deduction = round(base / (1 + r) * r, 2)
        if deduction <= 0:
            raise ValidationError('抵减额为 0，无法生成抵减凭证')

        deduct_acc = self._tour_vat_deduct_account()
        analytic = self._plan_analytic_distribution(self)
        journal = self._tour_get_journal('general')
        narration = '%s / %s / 差额征税抵减' % (self.plan_code or '-', self.plan_name or '')

        breakdown = self._plan_deductible_breakdown(self)
        total_ded = sum(breakdown.values()) or 0.0

        lines = [{
            'account_id': deduct_acc.id,
            'debit': deduction,
            'analytic': analytic,
            'compliance_ref': 'vat_diff',
            'name': '销项税额抵减 %s' % (self.plan_code or ''),
        }]
        # 贷方：按可扣除科目分摊（含税占比），尾差归最大科目，保证借贷平衡
        remaining = deduction
        items = sorted(breakdown.items(), key=lambda kv: -kv[1])
        for idx, (acc_id, amt) in enumerate(items):
            if idx == len(items) - 1:
                credit = round(remaining, 2)
            else:
                credit = round(deduction * amt / total_ded, 2)
                remaining -= credit
            if credit > 0:
                lines.append({
                    'account_id': acc_id,
                    'credit': credit,
                    'analytic': analytic,
                    'compliance_ref': 'vat_diff',
                    'name': '冲减成本(可扣除) %s' % (self.plan_code or ''),
                })

        move = self._tour_make_move(
            journal, self.end_date or fields.Date.context_today(self),
            self.plan_code, lines,
            compliance_ref='vat_diff', narration=narration)
        move.action_post()
        return move.id

    # === 成本账单生成 + 付款（P2P 模型方法，原仅在 run_ptp_posting.py 脚本内联）[E2E 闭环 GAP-3] ===

    def action_generate_cost_bill(self):
        """生成成本应付账单（幂等，cost_bill_id 判断）——借 6401 / 贷 2202，挂团分析账户。"""
        for rec in self:
            if rec.cost_bill_id:
                continue
            rec.cost_bill_id = rec._generate_cost_bill()

    def _generate_cost_bill(self):
        """生成供应商应付账单 account.move in_invoice [TDS §2.3]：
        借 6401 主营业务成本（out_sum 含税）/ 贷 2202 应付账款，均挂团分析账户；
        并同步建请款单 tour.pay.request（分级审批）。
        """
        self.ensure_one()
        amount = round(self.out_sum or 0.0, 2)
        if amount <= 0:
            raise ValidationError('团队 %s 无成本（out_sum=0），无法生成成本账单' % (self.plan_code or ''))
        if not self.supplier_id:
            raise ValidationError('团队 %s 未关联供应商，无法生成成本账单' % (self.plan_code or ''))
        if not self.analytic_account_id:
            self._ensure_analytic_account()
        analytic = self._plan_analytic_distribution(self)
        cost_acc = self._tour_get_account(self.ACCOUNT_COST)
        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_SUP)
        journal = self._tour_get_journal('purchase')
        product = self.env['product.product'].search([], limit=1)
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.supplier_id.id,
            'journal_id': journal.id,
            'invoice_date': self.end_date or fields.Date.context_today(self),
            'tour_plan_id': self.id,
            'ref': 'P2P-%s' % (self.plan_code or self.id),
            'compliance_ref': 'cas1',
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id if product else False,
                'name': '成本 %s' % (self.plan_code or self.id),
                'quantity': 1.0,
                'price_unit': amount,
                'account_id': cost_acc.id,
                'analytic_distribution': analytic,
                'tax_ids': [(6, 0, [])],
            })],
        })
        # 应付行强制落 2202 + 挂团分析账户
        move.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable').write({
                'account_id': payable_acc.id,
                'analytic_distribution': analytic,
            })
        move.action_post()
        # 同步建请款单（分级审批 state 机）
        self.env['tour.pay.request'].create({
            'plan_id': self.id,
            'supplier_id': self.supplier_id.id,
            'bill_id': move.id,
            'amount': amount,
            'cost_type': 'other',
            'cost_account_id': cost_acc.id,
            'reason': '团成本应付 %s' % (self.plan_code or self.id),
            'apply_date': self.end_date or fields.Date.context_today(self),
        }).action_approve()
        return move.id

    def action_pay_cost_bill(self):
        """付款成本账单（幂等，payment_state 判断）——借 2202 / 贷 1002，核销应付。"""
        for rec in self:
            rec._pay_cost_bill()

    def _pay_cost_bill(self):
        """付款：account.payment outbound（借 2202 / 贷 1002）+ 原生 reconcile 核销账单应付。"""
        self.ensure_one()
        bill = self.cost_bill_id
        if not bill or bill.payment_state == 'paid':
            return None
        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_SUP)
        bank_acc = self._tour_get_account(self.ACCOUNT_BANK)
        bank_journal = self._tour_get_journal('bank')
        if bank_journal.default_account_id.id != bank_acc.id:
            bank_journal.default_account_id = bank_acc.id
        pml = self.env['account.payment.method.line'].search(
            [('payment_type', '=', 'outbound'), ('journal_id', '=', bank_journal.id)], limit=1)
        if not pml:
            pml = self.env['account.payment.method.line'].search(
                [('payment_type', '=', 'outbound')], limit=1)
        if pml.payment_account_id.id != bank_acc.id:
            pml.payment_account_id = bank_acc.id
        pay = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': bill.partner_id.id,
            'amount': bill.amount_total,
            'journal_id': bank_journal.id,
            'payment_method_line_id': pml.id,
            'destination_account_id': payable_acc.id,
            'date': fields.Date.context_today(self),
        })
        pay.action_post()
        p_line = pay.move_id.line_ids.filtered(
            lambda l: l.account_id.id == payable_acc.id and l.debit > 0 and not l.reconciled)
        b_lines = bill.line_ids.filtered(
            lambda l: l.account_id.id == payable_acc.id and not l.reconciled)
        if p_line and b_lines:
            (p_line | b_lines).reconcile()
        pr = self.env['tour.pay.request'].search([('bill_id', '=', bill.id)], limit=1)
        if pr:
            pr.payment_id = pay.id
            if pr.state == 'approved':
                pr.action_pay()
        return pay.id

    def action_complete(self):
        """出行中 → 已完成：自动建台账 + 幂等确认收入（无金额时静默跳过，不阻断出团完成）。"""
        res = super().action_complete()
        for rec in self:
            if rec.state != 'completed':
                continue
            rec._ensure_plan_account()
            if not rec.income_move_id:
                existing = rec._existing_revenue_move()
                if existing:
                    rec.income_move_id = existing.id
                elif rec._revenue_amount() > 0:
                    rec.income_move_id = rec._generate_revenue_move()
        return res
