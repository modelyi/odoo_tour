# -*- coding: utf-8 -*-
from datetime import date

from odoo import models, fields, api
from odoo.exceptions import UserError


class TaReceivablePlanClaim(models.Model):
    """O2C 补全（迭代3）：期次核销扩展，挂在 ta_finance 侧，
    避免 ta_order 反向引用 ta.payment.claim。
    claim 审核时按 due_date 先到先核销期次；反审核按逆序回退。
    """
    _inherit = 'ta.receivable.plan'
    _description = '应收期次（认领核销扩展）'

    claim_ids = fields.Many2many('ta.payment.claim', 'ta_claim_plan_rel',
                                 'plan_id', 'claim_id', string='来源认领单', copy=False)

    def _allocate_paid(self, delta, claim=None):
        """把 delta 金额核销/回退到本期次（正=核销，负=回退）。"""
        self.ensure_one()
        new_paid = round(self.amount_paid + delta, 2)
        if new_paid < -0.01 or new_paid > self.amount + 0.01:
            raise UserError(
                f"期次「{self.name}」核销越界（已核 {self.amount_paid:.2f}，"
                f"应收 {self.amount:.2f}，本次 {delta:+.2f}）。")
        self.amount_paid = new_paid
        if claim:
            if delta > 0:
                self.claim_ids = [(4, claim.id)]
            elif not self.amount_paid:
                self.claim_ids = [(3, claim.id)]

    @api.model
    def _ta_apply_claim(self, order, amount, claim):
        """认领审核钩子：按到期日先到先核销 order 的未清期次，返回未分配余额。"""
        plans = order.plan_ids.sorted(lambda p: (p.due_date or date(9999, 12, 31), p.id))
        remain = round(amount, 2)
        for plan in plans:
            free = round(plan.amount - plan.amount_paid, 2)
            if remain <= 0.005 or free <= 0.005:
                continue
            take = min(free, remain)
            plan._allocate_paid(take, claim)
            remain = round(remain - take, 2)
        return remain

    @api.model
    def _ta_revert_claim(self, order, amount, claim):
        """反审核钩子：按核销逆序回退期次，返回未回退余额。"""
        plans = order.plan_ids.filtered(lambda p: p.amount_paid > 0.005)
        plans = plans.sorted(lambda p: (p.due_date or date(1, 1, 1), p.id), reverse=True)
        remain = round(amount, 2)
        for plan in plans:
            if remain <= 0.005:
                break
            back = min(round(plan.amount_paid, 2), remain)
            plan._allocate_paid(-back, claim)
            remain = round(remain - back, 2)
        return remain
