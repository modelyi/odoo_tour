# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaShopReturn(models.Model):
    """购物退单（BS-08 §4.2，菜单 [4303]）：客户退货 → 会计确认后冲减购物金额。

    确认动作（幂等，仅 draft→confirmed）：
    1. 校验退单金额 ≤ 原购物金额 − 该店其他已确认退单；
    2. 佣金单 draft → 按冲减后金额重算（引擎 upsert）；
       confirmed/settled → 已登记收款（AC-17）则拦截；否则红冲确认凭证
       （_reverse_moves，ref='退单红冲'），原单置 cancel，再生成新草稿单；
       借款冲抵凭证按公司级配置 ta_guide.commission_return_reverse_settle
       （默认 False=仅提示人工处理，True=自动反冲恢复借款）；
       红字发票随 BS-12 开票体系落地，本次仅 message_post 提示；
    3. 个税抵扣：按 原个税 × 退单金额/原购物金额 生成待抵扣记录（§4.2），
       下次同人佣金确认时自动抵减新个税（下限 0）。
    """
    _name = 'ta.shop.return'
    _description = '购物退单'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'return_date desc, id desc'

    name = fields.Char(string='退单编号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code(
                           'ta.shop.return') or '/')
    shop_id = fields.Many2one(
        'ta.shop', string='购物记录', required=True, tracking=True, ondelete='restrict',
        domain="[('state', '=', 'confirmed')]")
    departure_id = fields.Many2one(
        'ta.departure', related='shop_id.departure_id', store=True, string='发团计划')
    plan_code = fields.Char(related='shop_id.plan_code', string='计划号')
    shop_partner_id = fields.Many2one(
        'res.partner', related='shop_id.shop_partner_id', store=True, string='购物店')
    guide_id = fields.Many2one('res.partner', related='shop_id.guide_id', string='导游')
    shop_amount = fields.Float(
        related='shop_id.total_amount', string='原购物金额', digits=(15, 2))
    return_date = fields.Date(string='退单日期', required=True,
                              default=fields.Date.context_today, tracking=True)
    return_amount = fields.Float(string='退单金额', required=True, digits=(15, 2), tracking=True)
    reason = fields.Text(string='退单原因', required=True, tracking=True)
    state = fields.Selection([
        ('draft', '待审核'),
        ('confirmed', '已确认'),
        ('rejected', '已驳回'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    auditor_id = fields.Many2one('res.users', string='审核人', readonly=True, copy=False)
    audit_date = fields.Datetime(string='审核时间', readonly=True, copy=False)
    deduct_line_ids = fields.One2many(
        'ta.guide.commission.tax.deduct', 'return_id', string='个税抵扣记录')
    deduct_total = fields.Float(
        string='个税抵扣合计', compute='_compute_deduct_total', digits=(15, 2))

    @api.depends('deduct_line_ids.amount')
    def _compute_deduct_total(self):
        for r in self:
            r.deduct_total = round(sum(r.deduct_line_ids.mapped('amount')), 2)

    @api.constrains('return_amount')
    def _check_amount(self):
        for r in self:
            if r.return_amount <= 0:
                raise UserError("退单金额必须大于 0。")
            cap = r._confirmed_cap()
            if r.return_amount > cap + 0.005:
                raise UserError(
                    f"退单金额 {r.return_amount:.2f} 超过可退额度 {cap:.2f}"
                    f"（原购物金额 − 该店其他已确认退单）。")

    def _confirmed_cap(self):
        """可退额度 = 原购物金额 − 该购物记录其他已确认退单合计。"""
        self.ensure_one()
        others = self.search([
            ('shop_id', '=', self.shop_id.id),
            ('state', '=', 'confirmed'),
            ('id', '!=', self.id),
        ])
        return round(self.shop_id.total_amount
                     - sum(others.mapped('return_amount')), 2)

    def action_confirm(self):
        """确认退单：冲减购物金额 → 佣金红冲/重算 → 个税抵扣记录（见类注释）。"""
        for r in self:
            if r.state != 'draft':
                raise UserError("只有待审核的退单可以确认。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("退单确认需要会计权限。")
            cap = r._confirmed_cap()
            if r.return_amount > cap + 0.005:
                raise UserError(
                    f"退单金额 {r.return_amount:.2f} 超过可退额度 {cap:.2f}。")
            shop = r.shop_id
            commission = r._ta_handle_commissions(shop)
            r.state = 'confirmed'
            r.auditor_id = self.env.user
            r.audit_date = fields.Datetime.now()
            shop.message_post(body=(
                f"退单 {r.name} 已确认：退单金额 {r.return_amount:.2f}，"
                f"购物有效金额（总金额−已确认退单）由 {shop.total_amount:.2f} 调整为 "
                f"{shop.effective_amount:.2f}。"
                + (f"佣金单已重算：{commission.name}。" if commission else "")))
        return True

    def _ta_handle_commissions(self, shop):
        """红冲已确认佣金凭证 + 个税抵扣记录；返回重算后的佣金单（可空）。"""
        self.ensure_one()
        Commission = self.env['ta.guide.commission']
        commissions = Commission.search([
            ('departure_id', '=', shop.departure_id.id),
            ('shop_partner_id', '=', shop.shop_partner_id.id),
        ])
        active = commissions.filtered(lambda c: c.state in ('confirmed', 'settled'))
        reverse_settle = self.env['ir.config_parameter'].sudo().get_bool(
            'ta_guide.commission_return_reverse_settle', False)
        for c in active:
            received = round(sum(c.receipt_ids.mapped('amount')), 2)
            if received > 0.005:
                raise UserError(
                    f"佣金单 {c.name} 已登记收款 {received:.2f}（AC-17），"
                    f"请先冲销收款记录与凭证，再确认退单。")
            if c.move_id:
                rev = c.move_id._reverse_moves(default_values_list=[{
                    'ref': f"退单红冲 {self.name} / {c.name}",
                    'date': self.return_date,
                }])
                rev.action_post()
                c.message_post(body=(
                    f"退单 {self.name}：确认凭证已红冲（{rev[0].name if len(rev) == 1 else ''}），"
                    f"本单置为已取消，按冲减后金额生成新佣金单待确认。"))
            if c.settle_move_id:
                if reverse_settle:
                    rev2 = c.settle_move_id._reverse_moves(default_values_list=[{
                        'ref': f"退单反冲借款冲抵 {self.name} / {c.name}",
                        'date': self.return_date,
                    }])
                    rev2.action_post()
                    c.message_post(body=(
                        f"退单 {self.name}：借款冲抵凭证已按公司配置自动反冲，"
                        f"导游借款恢复冲抵前余额，请核对借款单状态。"))
                else:
                    c.message_post(body=(
                        f"退单 {self.name}：本单已结算冲抵借款。公司配置未开启自动反冲"
                        f"（ta_guide.commission_return_reverse_settle），"
                        f"请人工处理借款恢复与重新冲抵。"))
            c.message_post(body=(
                f"退单 {self.name} 红字发票提示：请按 BS-12 开票体系就该退单"
                f"开具红字发票（本系统本次仅提示，不做发票处理）。"))
            # 个税抵扣：原个税 × 退单金额/原购物金额（BS-08 §4.2）
            Deduct = self.env['ta.guide.commission.tax.deduct']
            for tr in c.tax_record_ids:
                if tr.tax_amount <= 0.005 or shop.total_amount <= 0:
                    continue
                amount = round(tr.tax_amount * self.return_amount / shop.total_amount, 2)
                if amount <= 0.005:
                    continue
                Deduct.create({
                    'tax_record_id': tr.id,
                    'return_id': self.id,
                    'staff_id': tr.staff_id.id,
                    'amount': amount,
                })
        active.write({'state': 'cancel'})
        # 有效购物金额已冲减（effective_amount）→ 引擎重算（draft 更新或新建草稿）
        return Commission._upsert_from_shop_group(shop)

    def action_reject(self):
        for r in self:
            if r.state != 'draft':
                raise UserError("只有待审核的退单可以驳回。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("退单驳回需要会计权限。")
            r.state = 'rejected'
            r.auditor_id = self.env.user
            r.audit_date = fields.Datetime.now()
        return True

    def action_request_tax_refund(self):
        """无后续佣金可抵扣时，将本退单未抵扣（pending）个税标记为申请退税。"""
        for r in self:
            if r.state != 'confirmed':
                raise UserError("只有已确认的退单可以申请退税。")
            pending = r.deduct_line_ids.filtered(lambda d: d.state == 'pending')
            if not pending:
                raise UserError("本退单没有待抵扣的个税记录。")
            pending.write({'state': 'refund_requested'})
            r.message_post(body=(
                f"已对 {len(pending)} 条未抵扣个税记录发起退税申请"
                f"（合计 {sum(pending.mapped('amount')):.2f}），请税务岗跟进。"))
        return True


class TaShopReturnFields(models.Model):
    """ta.shop 增加退单联动列：有效金额 = 总金额 − 已确认退单（佣金引擎口径）。"""
    _inherit = 'ta.shop'

    return_ids = fields.One2many('ta.shop.return', 'shop_id', string='退单')
    return_amount_total = fields.Float(
        string='已确认退单金额', compute='_compute_return_amount', store=True,
        digits=(15, 2),
        help='Σ 已确认退单金额（BS-08 §4.2）；驳回/待审核退单不计入。')
    effective_amount = fields.Float(
        string='有效购物金额', compute='_compute_return_amount', store=True,
        digits=(15, 2),
        help='= 购物总金额 − 已确认退单金额；佣金引擎按此计算返佣。')

    @api.depends('return_ids.return_amount', 'return_ids.state')
    def _compute_return_amount(self):
        for s in self:
            confirmed = s.return_ids.filtered(lambda r: r.state == 'confirmed')
            s.return_amount_total = round(sum(confirmed.mapped('return_amount')), 2)
            s.effective_amount = round(s.total_amount - s.return_amount_total, 2)


class TaGuideCommissionTaxDeduct(models.Model):
    """个税抵扣记录（BS-08 §4.2）：退单后已代缴个税的可抵扣额。

    amount = 原个税 × 退单金额 / 原购物金额；下次同人佣金确认时自动抵减
    新个税（下限 0，整条按金额顺序消耗，用不完留 pending）；无后续佣金可
    点「申请退税」（state → refund_requested）。
    """
    _name = 'ta.guide.commission.tax.deduct'
    _description = '退单个税抵扣'
    _inherit = ['ta.mixin']
    _order = 'id desc'

    tax_record_id = fields.Many2one(
        'ta.guide.commission.tax', string='原个税记录', required=True,
        ondelete='restrict', index=True)
    return_id = fields.Many2one(
        'ta.shop.return', string='退单', required=True, ondelete='cascade', index=True)
    staff_id = fields.Many2one('res.partner', string='人员', required=True)
    staff_name = fields.Char(related='staff_id.name', string='人员姓名')
    amount = fields.Float(string='可抵扣税额', required=True, digits=(15, 2))
    state = fields.Selection([
        ('pending', '待抵扣'),
        ('used', '已抵扣'),
        ('refund_requested', '已申请退税'),
    ], string='状态', default='pending', required=True, tracking=True)
    note = fields.Char(string='备注')

    def action_request_refund(self):
        for d in self:
            if d.state != 'pending':
                raise UserError("只有待抵扣的个税记录可以申请退税。")
            d.state = 'refund_requested'
        return True
