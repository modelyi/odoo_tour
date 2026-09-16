# -*- coding: utf-8 -*-
"""旅行社差额征税发票扩展（BS-12 Phase 1）。

- account.move 扩展：差额征税票面要素 + 团关联 + 开票状态（BS-12 §8.1）
- tour.invoice.deduct.line：差额扣除项目明细（BS-12 §8.2）

发票走 Odoo 原生 account.move，只做扩展，不重复造发票模型。
差额征税口径与 BS-11 Phase 3 一致（全额确认收入 + 成本侧 2221.03 抵减），
票面差额要素（差额销售额/扣除额/净税额）仅作票面展示，不另起分录 [BS-12 §3.2]。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountMoveTourInvoice(models.Model):
    _inherit = 'account.move'

    # === 发票类型（旅行社开票场景） ===
    tour_invoice_kind = fields.Selection([
        ('vat_special', '增值税专用发票'),
        ('vat_normal', '增值税普通发票'),
        ('vat_elec', '增值税电子普通发票'),
    ], string='发票类型', default='vat_normal',
       help='[财税2016-36号] 差额征税发票仅普票；专票仅全额计税+企业客户可抵扣场景')

    # === 差额征税发票标识 ===
    tour_is_diff_tax = fields.Boolean(
        '差额征税发票', default=False,
        help='[财税2016-36号] 票面标注"差额征税"，扣除项目金额以"***"体现')

    # === 差额征税票面要素（与 BS-11 §4 公式一致，票面展示用，不另起分录） ===
    tour_diff_gross = fields.Monetary(
        '全部价款(含税) G', currency_field='currency_id',
        help='= sum_pay_normal + sum_un_pay')
    tour_diff_deduct = fields.Monetary(
        '可扣除项目(含税) D', currency_field='currency_id',
        help='Σ 成本借方 where 科目.tour_vat_deductible=True 且有票')
    tour_diff_base = fields.Monetary(
        '差额销售额(不含税)', currency_field='currency_id',
        help='(G-D)÷(1+r)')
    tour_diff_tax = fields.Monetary(
        '销项税额(净额)', currency_field='currency_id',
        help='(G-D)÷(1+r)×r')

    # === 扣除项目明细（差额征税必备附表） ===
    tour_deduct_line_ids = fields.One2many(
        'tour.invoice.deduct.line', 'move_id', string='差额扣除明细')

    # === 团关联（开票口径：按团 / 按客户汇总） ===
    tour_plan_id = fields.Many2one(
        'tour.plan', string='关联团', index=True, help='按团开具口径')
    tour_plan_ids = fields.Many2many(
        'tour.plan', 'tour_invoice_plan_rel', 'move_id', 'plan_id',
        string='汇总开票的团', help='按客户汇总口径，多团合并开票')

    # === 开票进度状态（与原生 state 解耦） ===
    tour_invoice_state = fields.Selection([
        ('draft', '待申请'),
        ('applied', '已申请'),
        ('issued', '已开具'),
        ('void', '已作废'),
        ('reversed', '已红冲'),
    ], string='开票状态', default='draft', required=True)

    tour_invoice_apply_date = fields.Date('开票申请日期')
    tour_invoice_issue_date = fields.Date('开具日期')
    tour_invoice_no = fields.Char(
        '发票号码', related='name', readonly=False,
        help='复用 Odoo 原生发票号')

    @api.constrains('tour_is_diff_tax', 'tour_invoice_kind')
    def _check_diff_tax_kind(self):
        """[财税2016-36号] 差额征税发票不得开具增值税专用发票（BS-12 §3.3 系统强制校验）。"""
        for rec in self:
            if rec.tour_is_diff_tax and rec.tour_invoice_kind == 'vat_special':
                raise ValidationError(
                    '[财税2016-36号] 差额征税发票不得开具增值税专用发票')

    # ── 工作流按钮 ──────────────────────────────────────────────
    def action_apply(self):
        """提交开票申请 draft → applied [BS-12 §4.1]。"""
        for rec in self:
            rec.tour_invoice_state = 'applied'
            rec.tour_invoice_apply_date = fields.Date.context_today(rec)

    def action_cancel_apply(self):
        """撤回开票申请 applied → draft。"""
        for rec in self:
            rec.tour_invoice_state = 'draft'
            rec.tour_invoice_apply_date = False

    def action_issue(self):
        """审核通过并开具发票 applied → issued [BS-12 §4.1]。"""
        for rec in self:
            rec.tour_invoice_state = 'issued'
            rec.tour_invoice_issue_date = fields.Date.context_today(rec)

    def action_void(self):
        """作废发票 issued → void。"""
        for rec in self:
            rec.tour_invoice_state = 'void'

    def action_reverse(self):
        """红冲发票 issued → reversed。"""
        for rec in self:
            rec.tour_invoice_state = 'reversed'

    def action_post(self):
        """过账前把团维度落到应收行（挂团分析账户 + 落 1122.01 团款应收）[BS-12 §6.1/§6.2]。"""
        self._tour_propagate_receivable_analytic()
        return super().action_post()

    def _tour_propagate_receivable_analytic(self):
        """发票挂团 → 应收行(asset_receivable)挂团分析账户 + 应收科目落 1122.01。

        发票过账由 Odoo 原生生成应收行（out_invoice 的 asset_receivable 行），
        此处只补旅行社团维度，不重复造应收 [BS-12 §6.1/§5.2]。
        """
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            plan = move.tour_plan_id
            if not plan and move.tour_plan_ids:
                plan = move.tour_plan_ids[0]
            if not plan:
                continue
            analytic = {}
            aa = plan.analytic_account_id
            if aa:
                analytic = {str(aa.id): 100.0}
            # 应收账款—团款 1122.01（同 tour.accounting.mixin.ACCOUNT_RECEIVABLE_TOUR）
            rec_account = self.env['account.account'].search(
                [('code', '=', '1122.01')], limit=1)
            for line in move.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'):
                if rec_account and line.account_id.id != rec_account.id:
                    line.account_id = rec_account.id
                if analytic and not line.analytic_distribution:
                    line.analytic_distribution = analytic


class TourInvoiceDeductLine(models.Model):
    """差额征税扣除项目明细（BS-12 §8.2）。"""
    _name = 'tour.invoice.deduct.line'
    _description = '差额征税扣除项目明细'
    _order = 'id'

    move_id = fields.Many2one(
        'account.move', string='发票', required=True,
        ondelete='cascade', index=True)

    deduct_type = fields.Selection([
        ('lodging', '住宿费'),
        ('catering', '餐饮费'),
        ('traffic', '交通费'),
        ('ticket', '门票费'),
        ('visa', '签证费'),
        ('local_guide', '地接费'),
    ], string='扣除项目类型', required=True,
       help='[财税2016-36号] 6 类可差额扣除项目')

    amount = fields.Monetary(
        '含税金额', currency_field='currency_id', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='币种', related='move_id.currency_id',
        help='扣除明细币种随发票币种')

    account_id = fields.Many2one(
        'account.account', string='对应成本科目',
        domain="[('tour_vat_deductible', '=', True)]",
        help='溯源 tour_vat_deductible 科目')

    cost_move_line_id = fields.Many2one(
        'account.move.line', string='对应成本凭证行',
        help='溯源成本凭证，保证扣除项目有账可依')

    invoice_collected = fields.Boolean(
        '合规凭证已归集', default=False,
        help='[财税2016-36号] 无票部分不得参与差额扣除')

    _check_amount = models.Constraint(
        'check(amount >= 0)',
        '差额扣除项目含税金额不能为负',
    )
