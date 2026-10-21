# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import UserError, AccessError


GROSS_MODES = ('1', '12', '13', '14', '15', '21', '31')
NET_MODES = ('41',)


class TaRevenueRecognition(models.Model):
    """批6 P0-6 收入确认记录（发团日口径，BS-14 + BS-10 §7.2）。

    每发团计划至多一张（departure_id 唯一判重，幂等）：
    - 总额法（组团 1/12/13/14/15/21/31）：base=Σ有效订单含税金额；
      贷 6001.01=base/(1+r)、贷 2221.01=税；借客户应收科目（与收款认领贷方同科目
      同 partner 自然核销，认领代码不动）。
    - 净额法（41 代订）：diff=Σ订单−Σ已确认计调单；借 2241.01 代收代付 /
      贷 6001.03 差价；拆税开关打开时差价拆 6001.03 净额 + 2221.01 税。
    触发：发团动作钩子（公司配置 ta_revenue_auto_on_depart）+ 发团表单手动按钮。
    """
    _name = 'ta.revenue.recognition'
    _description = '收入确认'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    departure_id = fields.Many2one('ta.departure', string='发团计划', required=True,
                                   ondelete='restrict', index=True, readonly=True)
    date = fields.Date(string='确认日期', required=True, readonly=True,
                       help='收入确认时点=发团日（BS-10 §7.2）。')
    biz_mode_code = fields.Char(string='业务模式', readonly=True)
    mode = fields.Selection([
        ('gross', '总额法'),
        ('net', '净额法'),
    ], string='确认口径', required=True, readonly=True)
    gross_amount = fields.Float(string='收入基数（含税）', readonly=True,
                                digits=(12, 2))
    net_amount = fields.Float(string='确认收入（净额）', readonly=True,
                              digits=(12, 2))
    tax_amount = fields.Float(string='销项税额', readonly=True, digits=(12, 2))
    move_id = fields.Many2one('account.move', string='确认凭证', readonly=True,
                              copy=False)
    state = fields.Selection([
        ('posted', '已过账'),
        ('cancel', '已冲销'),
    ], string='状态', default='posted', required=True, readonly=True, copy=False)

    def action_cancel(self):
        """冲销收入确认：红冲凭证并作废记录（仅管理层，已核销收款不受影响）。"""
        for rec in self:
            if rec.state != 'posted':
                raise UserError("该收入确认已冲销。")
            if not self.env.user.has_group('ta_base.group_ta_manager'):
                raise AccessError("收入确认冲销需要管理层权限。")
            if rec.move_id:
                rev = rec.move_id._reverse_moves(default_values_list=[{
                    'ref': f"冲销收入确认 {rec.departure_id.code or ''}",
                    'date': fields.Date.context_today(rec),
                }])
                rev.action_post()
            rec.state = 'cancel'
        return True

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }


class TaDepartureRevenue(models.Model):
    _inherit = 'ta.departure'

    recognition_ids = fields.One2many('ta.revenue.recognition', 'departure_id',
                                      string='收入确认')

    def action_depart(self):
        res = super().action_depart()
        for dep in self:
            if dep.company_id.ta_revenue_auto_on_depart:
                dep.action_recognize_revenue()
        return res

    def action_recognize_revenue(self):
        """发团表单按钮：手动确认收入（幂等，已确认则直接返回）。"""
        created = self.env['ta.revenue.recognition']
        for dep in self:
            if dep.state not in ('departed', 'settled'):
                raise UserError("只有已发团/结算完成的发团计划可以确认收入。")
            if dep.recognition_ids.filtered(lambda r: r.state == 'posted'):
                continue
            vals = dep._ta_prepare_revenue_recognition()
            if vals:
                created |= self.env['ta.revenue.recognition'].create(vals)
        return created

    def _ta_prepare_revenue_recognition(self):
        """计算并落凭证（金额口径 BS-14 R 表；无金额可确认时返回空 dict）。"""
        self.ensure_one()
        amounts = self._ta_revenue_recognition_amounts()
        if not amounts:
            return {}
        move = self._ta_create_revenue_move(
            amounts['mode'], amounts['orders'],
            amounts['gross'], amounts['net'], amounts['tax'])
        return {
            'departure_id': self.id,
            'date': self.date_start,
            'biz_mode_code': amounts['mode_code'],
            'mode': amounts['mode'],
            'gross_amount': amounts['gross'],
            'net_amount': amounts['net'],
            'tax_amount': amounts['tax'],
            'move_id': move.id,
        }

    def _ta_revenue_recognition_amounts(self):
        """纯金额计算（不落凭证，供补记脚本 DRY_RUN 复用）。"""
        self.ensure_one()
        company = self.company_id
        mode_code = self.biz_mode_id.code or ''
        orders = self.env['ta.order'].search([
            ('departure_id', '=', self.id),
            ('state', 'in', ('confirmed', 'tripping', 'settled')),
        ])
        ord_sum = round(sum(orders.mapped('amount_total')), 2)
        if mode_code in GROSS_MODES:
            mode = 'gross'
            gross, net, tax = self._ta_revenue_gross(company, ord_sum)
        elif mode_code in NET_MODES:
            mode = 'net'
            dispatch_sum = round(sum(self.dispatch_item_ids.filtered(
                lambda i: i.state in ('confirmed', 'completed')).mapped('amount')), 2)
            diff = round(ord_sum - dispatch_sum, 2)
            if diff <= 0.005:
                return {}
            gross, net, tax = ord_sum, diff, 0.0
            if company.ta_revenue_dd_split_tax and company.ta_vat_rate:
                net = round(diff / (1 + company.ta_vat_rate), 2)
                tax = round(diff - net, 2)
        else:
            return {}
        if gross <= 0.005 and mode == 'gross':
            return {}
        return {
            'mode_code': mode_code,
            'mode': mode,
            'orders': orders,
            'gross': gross,
            'net': net,
            'tax': tax,
        }

    def _ta_revenue_gross(self, company, base):
        """总额法拆税：net=base/(1+r)，tax=base−net（r=0 则不拆税）。"""
        rate = company.ta_vat_rate or 0.0
        if rate:
            net = round(base / (1 + rate), 2)
            return base, net, round(base - net, 2)
        return base, base, 0.0

    def _ta_create_revenue_move(self, mode, orders, gross, net, tax):
        company = self.company_id
        acc_income = self._ta_get_account(
            '600101' if mode == 'gross' else '600103',
            '主营收入-组团' if mode == 'gross' else '主营收入-代订',
            'income')
        acc_tax = self._ta_get_account(
            '222101', '应交税费-应交增值税(销项税额)', 'liability_payable')
        acc_dd = self._ta_get_account(
            '224101', '其他应付款-代收代付', 'liability_current')
        acc_receivable_fb = self._ta_get_account(
            '1122', '应收账款', 'asset_receivable')
        lines = []
        if mode == 'gross':
            for order in orders:
                partner = order.partner_id.with_company(company)
                account = (partner.property_account_receivable_id
                           if order.partner_id else acc_receivable_fb)
                if not account:
                    account = acc_receivable_fb
                lines.append((0, 0, {
                    'name': f"收入确认 {self.code or ''} / {order.name}",
                    'partner_id': order.partner_id.id if order.partner_id else False,
                    'account_id': account.id,
                    'debit': order.amount_total,
                }))
        else:
            lines.append((0, 0, {
                'name': f"收入确认 {self.code or ''} 代订差价",
                'account_id': acc_dd.id,
                'debit': net + tax,
            }))
        lines.append((0, 0, {
            'name': f"收入确认 {self.code or ''}",
            'account_id': acc_income.id,
            'credit': net,
        }))
        if tax:
            lines.append((0, 0, {
                'name': f"收入确认 {self.code or ''} 销项税",
                'account_id': acc_tax.id,
                'credit': tax,
            }))
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1) \
            or self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        if not journal:
            raise UserError("当前公司没有销售/杂项日记账，无法生成收入确认凭证。")
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date_start,
            'ref': f"收入确认 {self.code or self.name}",
            'line_ids': lines,
        })
        move.action_post()
        return move
