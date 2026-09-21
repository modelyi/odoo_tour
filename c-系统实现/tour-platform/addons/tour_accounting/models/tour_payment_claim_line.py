# -*- coding: utf-8 -*-
"""团款收款认领明细行（BS-12 §8.5 / §6.2）。

- tour.payment.claim.line：收款登记行，把一笔收款（tour.payment.claim）
  拆分认领到具体发票（account.move out_invoice），回链核销溯源。
- account.move.tour_claim_line_ids：发票 → 收款认领反向回链（闭环）。
- tour.payment.claim.claim_line_ids：收款 → 明细行正向一对多。

发票/应收走 Odoo 原生 account（out_invoice 的 1122.01 行），
本模型只做「收款认领 → 发票」的核销溯源薄扩展，不重复造收款/核销。
金额字段用 Float（tour 体系金额全 Float，与 tour.payment.claim 一致）。
"""
from odoo import fields, models


class TourPaymentClaimLine(models.Model):
    _name = 'tour.payment.claim.line'
    _description = '收款认领明细行'
    _order = 'id'

    claim_id = fields.Many2one(
        'tour.payment.claim', string='收款登记', required=True,
        ondelete='cascade', index=True,
        help='所属收款登记（一笔收款可拆分认领到多张发票）')

    invoice_id = fields.Many2one(
        'account.move', string='核销的发票', index=True,
        domain="[('move_type', '=', 'out_invoice')]",
        help='收款认领核销到具体发票的应收行 [BS-12 §6.2 闭环溯源]')

    amount = fields.Float(
        '认领金额', digits=(16, 2), default=0.0,
        help='该笔收款拆分认领到本张发票的金额')

    name = fields.Char('说明', help='认领/核销摘要')

    _check_amount = models.Constraint(
        'check(amount >= 0)',
        '收款认领金额不能为负',
    )


class TourPaymentClaimLineParent(models.Model):
    """收款登记正向一对多：收款 → 明细行。"""
    _inherit = 'tour.payment.claim'

    claim_line_ids = fields.One2many(
        'tour.payment.claim.line', 'claim_id', string='收款认领明细')


class AccountMoveTourClaim(models.Model):
    """发票反向回链：发票 → 收款认领明细（闭环溯源）。"""
    _inherit = 'account.move'

    tour_claim_line_ids = fields.One2many(
        'tour.payment.claim.line', 'invoice_id', string='关联收款认领',
        help='反向查该发票被哪些收款认领核销 [BS-12 §6.2]')
