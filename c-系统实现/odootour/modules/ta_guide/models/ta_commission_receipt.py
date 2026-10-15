# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaCommissionReceipt(models.Model):
    """佣金收款（BS-08 AC-17 菜单 [3622]）：购物店支付佣金款的到账登记。

    凭证：借 收款日记账默认科目（银行/现金）/ 贷 1222 其他应收款-购物佣金
    （与佣金确认凭证借方同科目同 partner，闭环核销）。
    收款与 settled（借款冲抵，AC-18）正交：已结算佣金单仍可收款。
    """
    _name = 'ta.commission.receipt'
    _description = '佣金收款'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='收款编号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code(
                           'ta.commission.receipt') or '/')
    commission_id = fields.Many2one(
        'ta.guide.commission', string='佣金单', required=True, tracking=True,
        domain="[('shop_partner_id', '!=', False)]", ondelete='restrict')
    commission_name = fields.Char(related='commission_id.name', string='佣金单号')
    shop_partner_id = fields.Many2one(
        related='commission_id.shop_partner_id', string='购物店', store=True)
    guide_id = fields.Many2one(related='commission_id.guide_id', string='导游')
    date = fields.Date(string='收款日期', required=True,
                       default=fields.Date.context_today, tracking=True)
    amount = fields.Float(string='收款金额', required=True, digits=(15, 2), tracking=True)
    journal_id = fields.Many2one(
        'account.journal', string='收款日记账', required=True, tracking=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    move_id = fields.Many2one('account.move', string='收款凭证', readonly=True, copy=False)
    remark = fields.Char(string='备注')

    @api.constrains('amount')
    def _check_amount(self):
        for r in self:
            if r.amount <= 0:
                raise UserError("收款金额必须大于 0。")

    def init(self):
        # 模型初始化次序不保证对账视图后建：本表落库后重建对账视图挂已收列。
        from .ta_shop_reconciliation import _ta_shop_reconciliation_view_sql
        self.env.cr.execute("DROP VIEW IF EXISTS ta_shop_reconciliation")
        self.env.cr.execute(_ta_shop_reconciliation_view_sql(self.env.cr))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            commission = self.env['ta.guide.commission'].browse(vals['commission_id'])
            if not commission.shop_partner_id:
                raise UserError("手工路径佣金单没有购物店应收，不能登记收款。")
            if commission.state not in ('confirmed', 'settled'):
                raise UserError("只有已确认/已结算的佣金单可以登记收款。")
            received = sum(commission.receipt_ids.mapped('amount'))
            limit = round(commission.commission_total - received, 2)
            if vals.get('amount', 0.0) > limit + 0.005:
                raise UserError(
                    f"收款金额 {vals.get('amount', 0.0):.2f} 超过佣金单 "
                    f"{commission.name} 未收余额 {limit:.2f}。")
            vals['move_id'] = self._create_receipt_move(commission, vals).id
        return super().create(vals_list)

    def _create_receipt_move(self, commission, vals):
        """借 收款日记账默认科目 / 贷 1222 购物佣金应收（同 partner 闭环）。
        create() 阶段尚无记录：model 级方法，不走 ensure_one。"""
        journal = self.env['account.journal'].browse(vals['journal_id'])
        if not journal.default_account_id:
            raise UserError(
                f"收款日记账 {journal.name} 未配置默认科目，无法生成收款凭证。")
        acc_receivable = commission._get_commission_account(
            '1222', '其他应收款-购物佣金', 'asset_receivable', ['购物佣金'],
            reconcile=True)
        amount = vals.get('amount', 0.0)
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': vals.get('date') or fields.Date.context_today(self),
            'ref': f"佣金收款 {commission.name} / {commission.shop_partner_id.name}",
            'line_ids': [
                (0, 0, {'name': f"佣金收款 {commission.name}",
                        'partner_id': commission.shop_partner_id.id,
                        'account_id': journal.default_account_id.id,
                        'debit': amount}),
                (0, 0, {'name': f"佣金收款 {commission.name} 购物店应收",
                        'partner_id': commission.shop_partner_id.id,
                        'account_id': acc_receivable.id,
                        'credit': amount}),
            ],
        })
        move.action_post()
        return move

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }


class TaCommissionCollectWizard(models.TransientModel):
    """购物批量收款向导（BS-08 AC-17 菜单 [3622]）：多选佣金单一次收款。

    行金额默认 = 佣金总额 − 已收（含 0 则不预填该单）；提交逐单生成收款记录
    与凭证，单笔超额即整单拦截（用户改金额后重试）。
    """
    _name = 'ta.commission.collect.wizard'
    _description = '购物批量收款'

    date = fields.Date(string='收款日期', required=True,
                       default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='收款日记账',
        domain="[('type', 'in', ('bank', 'cash'))]")
    line_ids = fields.One2many(
        'ta.commission.collect.wizard.line', 'wizard_id', string='佣金单')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        commission_ids = self.env.context.get('active_ids') or []
        if self.env.context.get('default_commission_id'):
            commission_ids = [self.env.context['default_commission_id']]
        lines = []
        for commission in self.env['ta.guide.commission'].browse(commission_ids):
            if not commission.shop_partner_id:
                continue
            if commission.state not in ('confirmed', 'settled'):
                continue
            remaining = round(commission.commission_total
                              - sum(commission.receipt_ids.mapped('amount')), 2)
            if remaining <= 0.005:
                continue
            lines.append((0, 0, {
                'commission_id': commission.id,
                'amount': remaining,
            }))
        if lines:
            res['line_ids'] = lines
        return res

    def action_collect(self):
        self.ensure_one()
        if not self.journal_id:
            raise UserError("请先选择收款日记账。")
        receipts = self.env['ta.commission.receipt']
        for line in self.line_ids:
            if line.amount <= 0:
                continue
            receipts += self.env['ta.commission.receipt'].create({
                'commission_id': line.commission_id.id,
                'date': self.date,
                'amount': line.amount,
                'journal_id': self.journal_id.id,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': '佣金收款',
            'res_model': 'ta.commission.receipt',
            'view_mode': 'list,form',
            'domain': [('id', 'in', receipts.ids)],
        }


class TaCommissionCollectWizardLine(models.TransientModel):
    _name = 'ta.commission.collect.wizard.line'
    _description = '购物批量收款行'

    wizard_id = fields.Many2one(
        'ta.commission.collect.wizard', ondelete='cascade', required=True)
    commission_id = fields.Many2one(
        'ta.guide.commission', string='佣金单', required=True, readonly=True)
    shop_partner_id = fields.Many2one(
        related='commission_id.shop_partner_id', string='购物店')
    guide_id = fields.Many2one(related='commission_id.guide_id', string='导游')
    commission_total = fields.Float(
        related='commission_id.commission_total', string='佣金总额')
    received_total = fields.Float(
        related='commission_id.received_total', string='已收金额')
    amount = fields.Float(string='本次收款', digits=(15, 2), required=True)


class TaGuideCommissionReceipt(models.Model):
    _inherit = 'ta.guide.commission'

    receipt_ids = fields.One2many(
        'ta.commission.receipt', 'commission_id', string='佣金收款')
    received_total = fields.Float(
        string='已收佣金', compute='_compute_received', digits=(15, 2),
        help='Σ 已登记收款金额（AC-17）；与借款冲抵（settled）正交。')

    @api.depends('receipt_ids.amount')
    def _compute_received(self):
        for c in self:
            c.received_total = round(sum(c.receipt_ids.mapped('amount')), 2)

    def action_collect_receipt(self):
        """佣金单表单「收款」按钮：打开批量收款向导（单笔预填）。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '佣金收款',
            'res_model': 'ta.commission.collect.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_commission_id': self.id},
        }
