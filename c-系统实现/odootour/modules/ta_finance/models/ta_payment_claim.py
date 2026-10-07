# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaPaymentClaim(models.Model):
    """收款认领单（三步闭环第 2 步发起、第 3 步审核）。

    AC-05（BS-06）：登记人 ≠ 认领人 ≠ 审核人，系统级拦截。
    NFR-2：审核生成凭证幂等——move_id 已有值的单据不能再次审核。
    """
    _name = 'ta.payment.claim'
    _description = '收款认领单'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='认领单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.payment.claim') or '/')
    date = fields.Date(required=True, default=fields.Date.context_today)
    claimed_by = fields.Many2one('res.users', string='认领人', readonly=True,
                                 default=lambda self: self.env.user, required=True)
    approved_by = fields.Many2one('res.users', string='审核人', readonly=True, copy=False)
    line_ids = fields.One2many('ta.claim.line', 'claim_id', string='资金来源（银行到账）')
    alloc_ids = fields.One2many('ta.claim.alloc', 'claim_id', string='认领去向（订单）')
    amount = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_alloc = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency', store=True)
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '待审核'),
        ('approved', '已审核'),
        ('rejected', '已驳回'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='生成凭证', readonly=True, copy=False)
    note = fields.Char()
    # 批4-B 搜索辅助：认领单没有直接的订单/客户字段，按认领去向聚合
    # （store=True 才能进 search view 过滤）。
    order_ids = fields.Many2many(
        'ta.order', string='认领订单', compute='_compute_search_refs', store=True)
    partner_ids = fields.Many2many(
        'res.partner', string='认领客户', compute='_compute_search_refs', store=True)

    @api.depends('alloc_ids.order_id')
    def _compute_search_refs(self):
        for claim in self:
            orders = claim.alloc_ids.order_id
            claim.order_ids = orders
            claim.partner_ids = orders.partner_id

    @api.depends('line_ids.bank_line_id.currency_id')
    def _compute_currency(self):
        for claim in self:
            cur = claim.line_ids.mapped('bank_line_id.currency_id')
            claim.currency_id = cur[0] if len(cur) == 1 else self.env.company.currency_id

    @api.depends('line_ids.amount', 'alloc_ids.amount_allocated')
    def _compute_amounts(self):
        for claim in self:
            claim.amount = sum(claim.line_ids.mapped('amount'))
            claim.amount_alloc = sum(claim.alloc_ids.mapped('amount_allocated'))

    # ---- 步骤 2：提交 ----
    def action_submit(self):
        for claim in self:
            if claim.state not in ('draft', 'rejected'):
                raise UserError("只有草稿或被驳回的认领单可以提交。")
            if not claim.line_ids or not claim.alloc_ids:
                raise UserError("资金来源与认领去向都不能为空。")
            if abs(claim.amount - claim.amount_alloc) > 0.01:
                raise UserError("来源与去向金额不平衡。")
            for cl in claim.line_ids:
                reserved = cl.bank_line_id.amount_reserved()
                if cl.amount + reserved > cl.bank_line_id.amount + 0.01:
                    raise UserError(
                        f"流水 {cl.bank_line_id.ref or cl.bank_line_id.id} 可认领余额不足。")
            if claim.company_id != self.env.company:
                raise AccessError("不允许跨公司操作认领单。")
            claim.state = 'submitted'

    # ---- 步骤 3：审核（通过后落账）----
    def action_approve(self):
        for claim in self:
            if claim.state != 'submitted':
                raise UserError("只有待审核的认领单可以审核。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("认领审核需要会计/财务经理权限。")
            if claim.move_id:  # NFR-2 幂等双保险
                raise UserError("该认领单已生成凭证，不能重复审核。")
            self._check_separation(claim)
            for cl in claim.line_ids:
                if cl.amount > cl.bank_line_id.residual + 0.01:
                    raise UserError(f"流水 {cl.bank_line_id.ref or cl.bank_line_id.id} 已被其他审核占用。")
            for alloc in claim.alloc_ids:
                alloc.order_id._ta_apply_paid(alloc.amount_allocated)
                # 期次核销：先到期先分配；历史订单期次不全时余量仅记订单头，不拦截
                self.env['ta.receivable.plan']._ta_apply_claim(
                    alloc.order_id, alloc.amount_allocated, claim)
            claim.move_id = claim._create_move()
            claim.approved_by = self.env.user
            claim.state = 'approved'
        return True

    def action_reject(self):
        for claim in self:
            if claim.state != 'submitted':
                raise UserError("只有待审核的认领单可以驳回。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("认领审核需要会计/财务经理权限。")
            self._check_separation(claim)
            claim.state = 'rejected'

    def action_reverse(self):
        """反审核：冲销凭证并回退订单已收款（红冲路径，不允许直改）。"""
        for claim in self:
            if claim.state != 'approved':
                raise UserError("只有已审核的认领单可以反审核。")
            if not self.env.user.has_group('ta_base.group_ta_manager'):
                raise AccessError("反审核需要管理层权限。")
            if claim.move_id:
                rev = claim.move_id._reverse_moves(
                    default_values_list=[{
                        'ref': f"反审核 {claim.name}",
                        'date': fields.Date.context_today(claim),
                    }])
                rev.action_post()
            for alloc in claim.alloc_ids:
                self.env['ta.receivable.plan']._ta_revert_claim(
                    alloc.order_id, alloc.amount_allocated, claim)
                alloc.order_id._ta_apply_paid(-alloc.amount_allocated)
            claim.write({'state': 'draft', 'move_id': False, 'approved_by': False})

    def _check_separation(self, claim):
        me = self.env.user
        if me == claim.claimed_by:
            raise AccessError("审核人不能是认领人（AC-05 岗位分离）。")
        registrants = claim.line_ids.mapped('bank_line_id.registered_by')
        if me in registrants:
            raise AccessError("审核人不能是该笔到账的登记人（AC-05 岗位分离）。")

    def _create_move(self):
        self.ensure_one()
        journal = self.line_ids[0].bank_line_id.journal_id
        if not journal.default_account_id:
            raise UserError(f"日记账「{journal.name}」未设置默认科目，无法落账。")
        vals_lines = []
        total = 0.0
        for alloc in self.alloc_ids:
            order = alloc.order_id
            partner = order.partner_id
            if not partner:
                raise UserError(f"订单 {order.name} 未指定客户，无法记应收账款。")
            receivable = partner.with_company(self.company_id).property_account_receivable_id
            if not receivable:
                raise UserError("客户未配置应收科目（检查科目表/公司设置）。")
            vals_lines.append((0, 0, {
                'name': f"收款认领 {self.name} / {order.name}",
                'partner_id': partner.id,
                'account_id': receivable.id,
                'credit': alloc.amount_allocated,
            }))
            total += alloc.amount_allocated
        vals_lines.append((0, 0, {
            'name': f"收款认领 {self.name}",
            'account_id': journal.default_account_id.id,
            'debit': total,
        }))
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date,
            'ref': f"{self.name} {self.line_ids[0].bank_line_id.ref or ''}".strip(),
            'line_ids': vals_lines,
        })
        move.action_post()
        return move


class TaClaimLine(models.Model):
    _name = 'ta.claim.line'
    _description = '认领来源行'
    _inherit = ['ta.mixin']

    claim_id = fields.Many2one('ta.payment.claim', ondelete='cascade', required=True)
    bank_line_id = fields.Many2one('ta.bank.line', string='银行到账', required=True,
                                   domain="[('state', '!=', 'claimed')]")
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='币种', related='claim_id.currency_id', store=True)
    claim_state = fields.Selection(related='claim_id.state', string='认领单状态')


class TaClaimAlloc(models.Model):
    _name = 'ta.claim.alloc'
    _description = '认领去向行'
    _inherit = ['ta.mixin']

    claim_id = fields.Many2one('ta.payment.claim', ondelete='cascade', required=True)
    order_id = fields.Many2one('ta.order', string='订单', required=True,
                               domain="[('state', 'in', ('confirmed', 'tripping'))]")
    amount_allocated = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='币种', related='claim_id.currency_id', store=True)
