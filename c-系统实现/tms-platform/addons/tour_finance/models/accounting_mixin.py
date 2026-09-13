# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError


class TourAccountingMixin(models.AbstractModel):
    """旅行社记账公共方法（对接 Odoo account 原生复式记账）。

    资金/往来/收入/成本的一切金额流转都落到 account.move（借贷平衡），
    tour.* 自研金额字段只作业务口径快照，不作记账依据 [BS-10 P1]。
    """
    _name = 'tour.accounting.mixin'
    _description = '旅行社记账公共方法'

    # === 科目编码常量（与 data/account_account_tour.xml 对齐，BS-10 §四）===
    ACCOUNT_CASH = '1001'              # 库存现金
    ACCOUNT_BANK = '1002'              # 银行存款
    ACCOUNT_OTHER_MONETARY = '1012'    # 其他货币资金（微信/支付宝）
    ACCOUNT_PREPAY_TOUR = '2203.01'    # 预收账款—团款
    ACCOUNT_PREPAY = '2203'            # 预收账款（兜底）
    ACCOUNT_COST_GUIDE = '6401.07'     # 成本—导服费（佣金计提借方）
    ACCOUNT_PAYABLE_GUIDE = '2241.02'  # 其他应付款—导游分成
    ACCOUNT_TAX_IIT = '2221.05'        # 应交税费—应交个人所得税
    ACCOUNT_FINANCE_EXPENSE = '6603'   # 财务费用（手续费）
    ACCOUNT_RECEIVABLE_TOUR = '1122.01'    # 应收账款—团款（对账差异调整借方）
    ACCOUNT_REVENUE_GROSS = '6001.01'      # 主营收入—组团（总额法）
    ACCOUNT_REVENUE_NET_DT = '6001.02'     # 主营收入—地接（净额法差价）
    ACCOUNT_REVENUE_NET_DD = '6001.03'     # 主营收入—代订（净额法差价）
    ACCOUNT_TAX_OUTPUT = '2221.01'         # 应交增值税(销项) — 一般纳税人销项税额 [BS-11 §六]
    ACCOUNT_TAX_DEDUCT = '2221.03'         # 应交增值税(销项税额抵减/差额扣除) [BS-11 §六]
    ACCOUNT_TAX_SIMPLE = '2221.07'         # 应交增值税(简易计税/小规模) [BS-11 §六]

    # 收入确认模式：总额法（主要责任人 DTO/DSO）vs 净额法（代理人 DT/DSK/DSN/DD）[BS-10 §7.2]
    REVENUE_GROSS_MODES = ('21', '31')   # 组团团队 DTO / 组团散客 DSO → 总额法
    REVENUE_DD_MODES = ('41',)           # 代订项目 DD → 净额法（6001.03 代订收入）

    def _get_company_currency(self):
        return self.env.company.currency_id

    def _tour_get_account(self, code):
        """按科目编码查 account.account（code_store 反查，不写死 id）。"""
        account = self.env['account.account'].search([('code', '=', code)], limit=1)
        if not account:
            raise UserError(
                '未找到会计科目编码「%s」，请先安装/配置旅行社科目表'
                '（l10n_cn 企业准则 + tour_finance 明细科目）' % code)
        return account

    def _tour_get_journal(self, journal_type='general'):
        """按类型取日记账；找不到回退到公司任意日记账，再回退抛错。"""
        journal = self.env['account.journal'].search(
            [('type', '=', journal_type),
             ('company_id', 'in', (self.env.company.id, False))], limit=1)
        if not journal:
            journal = self.env['account.journal'].search(
                [('company_id', 'in', (self.env.company.id, False))], limit=1)
        if not journal:
            raise UserError('未找到可用日记账，请先在会计模块配置日记账')
        return journal

    def _plan_analytic_distribution(self, plan):
        """返回单团 analytic_distribution dict；plan 无分析账户时返回空。

        Odoo 19 恒为 {str(analytic_account_id): 100.0}（单分析计划）[TDS §7.2]。
        """
        if not plan:
            return {}
        aa = plan.analytic_account_id
        return {str(aa.id): 100.0} if aa else {}

    # === Phase 2：金额派生（account.move.line / account.analytic.line 为记账真相）===

    def _plan_analytic_lines(self, plan, account_ids=None):
        """返回该团（analytic account）的分析行；可按财务科目过滤。

        记账真相 = account.analytic.line（由凭证行 analytic_distribution 过账生成），
        用于单团收入/成本汇总 [TDS §4.3]。
        """
        if not plan or not plan.analytic_account_id:
            return self.env['account.analytic.line']
        domain = [('account_id', '=', plan.analytic_account_id.id)]
        if account_ids:
            domain.append(('general_account_id', 'in', account_ids))
        return self.env['account.analytic.line'].search(domain)

    def _plan_open_move_lines(self, plan, account_ids=None, partner_id=None,
                              date_from=None, date_to=None, reconciled=None):
        """返回该团（analytic）的已过账凭证行；默认只取未核销（open）行。

        通过 analytic_line_ids 反查（EXISTS 子查询），避免直接操作 JSON 字段。
        """
        if not plan or not plan.analytic_account_id:
            return self.env['account.move.line']
        domain = [
            ('parent_state', '=', 'posted'),
            ('analytic_line_ids.account_id', '=', plan.analytic_account_id.id),
        ]
        if reconciled is not None:
            domain.append(('reconciled', '=', reconciled))
        if account_ids:
            domain.append(('account_id', 'in', account_ids))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        return self.env['account.move.line'].search(domain)

    def _plan_prepay_balance(self, plan):
        """该团未核销的预收团款（2203.01）残值（正数，收入确认/台账预收的金额来源）。

        预收为贷方，amount_residual 为负，取绝对值表示应结转的预收金额。
        """
        accs = self.env['account.account'].search(
            [('code', 'in', (self.ACCOUNT_PREPAY_TOUR, self.ACCOUNT_PREPAY))])
        if not accs:
            return 0.0
        lines = self._plan_open_move_lines(
            plan, account_ids=accs.ids,
            partner_id=plan.supplier_id.id if plan.supplier_id else None)
        return abs(sum(lines.mapped('amount_residual'))) if lines else 0.0

    def _tour_reconcile_account_ids(self):
        """往来科目 id 列表（应收/预付/应付/预收/其他往来），用于对账派生。

        排除 asset_cash（银行/现金虽 reconcile=True 但属银行对账，不参与往来对账）。
        """
        return self.env['account.account'].search([
            ('account_type', 'in', (
                'asset_receivable', 'asset_prepayments',
                'liability_payable', 'liability_current')),
        ]).ids

    def _partner_move_lines(self, partner_id, account_ids=None, date_from=None,
                            date_to=None, analytic_account_id=None, reconciled=None):
        """返回某往来方（partner）的已过账凭证行；可按科目/期间/团/是否核销过滤。"""
        domain = [('parent_state', '=', 'posted')]
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        if account_ids:
            domain.append(('account_id', 'in', account_ids))
        if analytic_account_id:
            domain.append(('analytic_line_ids.account_id', '=', analytic_account_id))
        if reconciled is not None:
            domain.append(('reconciled', '=', reconciled))
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        return self.env['account.move.line'].search(domain)

    def _plan_analytic_balance(self, plan):
        """汇总该团收入/成本（从分析行）。

        Odoo 19 分析行金额符号：贷方（收入/负债贷）为正，借方（成本/资产借）为负。
        返回 (income, cost) 均为正数：income = Σ income 分析行，cost = -Σ expense 分析行。
        """
        income = cost = 0.0
        for ln in self._plan_analytic_lines(plan):
            acc = ln.general_account_id or (ln.move_line_id.account_id if ln.move_line_id else False)
            atype = acc.account_type if acc else False
            amt = ln.amount or 0.0
            if atype in ('income', 'income_other'):
                income += amt
            elif atype in ('expense', 'expense_direct_cost', 'expense_depreciation'):
                cost += amt
        return (income, -cost)  # cost 分析行为负，取反得正数

    # === Phase 3：差额征税增值税（拆税/抵减/纳税人配置）[BS-11] ===

    def _tour_vat_params(self):
        """返回 (taxpayer_type, rate, enabled)。rate 为百分数（6/3/1），计算税额时 ÷100。

        - 一般纳税人 → tour_vat_rate（默认 6%）
        - 小规模纳税人 → tour_vat_levy_rate（默认 3%，优惠期调 1%）
        [BS-11 §10.3]
        """
        co = self.env.company
        if co.tour_taxpayer_type == 'general':
            rate = co.tour_vat_rate or 0.0
        else:
            rate = co.tour_vat_levy_rate or 0.0
        return co.tour_taxpayer_type, rate, co.tour_diff_tax_enabled

    def _tour_vat_account(self):
        """销项税科目：一般→2221.01（销项），小规模→2221.07（简易计税）[BS-11 §10.3]"""
        return self._tour_get_account(
            self.ACCOUNT_TAX_OUTPUT if self.env.company.tour_taxpayer_type == 'general'
            else self.ACCOUNT_TAX_SIMPLE)

    def _tour_vat_deduct_account(self):
        """销项税额抵减科目：一般→2221.03（抵减专栏），小规模→2221.07（单一科目）[BS-11 §4.3/§7.2]"""
        return self._tour_get_account(
            self.ACCOUNT_TAX_DEDUCT if self.env.company.tour_taxpayer_type == 'general'
            else self.ACCOUNT_TAX_SIMPLE)

    def _plan_cost_vat_split(self, plan):
        """返回 (cost_deductible, cost_non_deductible)：按 tour_vat_deductible 从分析行归集（含税口径，正数）。

        可扣除 = 科目.tour_vat_deductible=True 的成本借方；不可扣除 = False [BS-11 §8.2]。
        """
        deductible = non_deductible = 0.0
        for ln in self._plan_analytic_lines(plan):
            acc = ln.general_account_id or (ln.move_line_id.account_id if ln.move_line_id else False)
            if not acc or acc.account_type not in ('expense', 'expense_direct_cost', 'expense_depreciation'):
                continue
            amt = abs(ln.amount or 0.0)
            if acc.tour_vat_deductible:
                deductible += amt
            else:
                non_deductible += amt
        return deductible, non_deductible

    def _plan_deductible_breakdown(self, plan):
        """{account_id: 含税金额} 可扣除成本按科目归集（抵减凭证贷方分摊依据）[BS-11 §7.2.2]"""
        breakdown = {}
        for ln in self._plan_analytic_lines(plan):
            acc = ln.general_account_id or (ln.move_line_id.account_id if ln.move_line_id else False)
            if not acc or not acc.tour_vat_deductible:
                continue
            if acc.account_type not in ('expense', 'expense_direct_cost', 'expense_depreciation'):
                continue
            breakdown[acc.id] = breakdown.get(acc.id, 0.0) + abs(ln.amount or 0.0)
        return breakdown

    def _tour_make_move(self, journal, date, ref, lines, move_type='entry',
                        compliance_ref=False, narration=None):
        """生成 account.move（复式分录，借贷平衡由 Odoo 强制校验）。

        lines: list[dict]，键：
            account_id (int) 必填
            partner_id (int) 可选
            debit / credit (float) 二选一
            analytic (dict) 可选 analytic_distribution
            compliance_ref (str) 可选 行级准则依据（覆盖主凭证标签）
            name (str) 可选 行摘要
        """
        move_vals = {
            'move_type': move_type,
            'journal_id': journal.id,
            'date': date,
            'ref': ref,
            'compliance_ref': compliance_ref,
            'line_ids': [],
        }
        if narration:
            move_vals['narration'] = narration
        for ln in lines:
            move_vals['line_ids'].append((0, 0, {
                'account_id': ln['account_id'],
                'partner_id': ln.get('partner_id'),
                'debit': ln.get('debit', 0.0),
                'credit': ln.get('credit', 0.0),
                'analytic_distribution': ln.get('analytic') or {},
                'compliance_ref': ln.get('compliance_ref'),
                'name': ln.get('name', ref),
            }))
        return self.env['account.move'].create(move_vals)
