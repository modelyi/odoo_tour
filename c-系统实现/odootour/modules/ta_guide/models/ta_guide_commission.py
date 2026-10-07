# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


def _calc_labor_tax(amount):
    """劳务报酬预扣个税 [个税法-劳务报酬 / BS-08 §4.9]：
    - 单次 ≤ 800 元：不预扣
    - 800 < 单次 ≤ 4000 元：预扣 = (单次 - 800) × 20%
    - 单次 > 4000 元：预扣 = 单次 × (1-20%) × 适用税率 - 速算扣除数
      （≤20000：20%/0；20000-50000：30%/2000；>50000：40%/7000）
    """
    if amount <= 800:
        return 0.0
    if amount <= 4000:
        return round((amount - 800) * 0.20, 2)
    taxable = amount * (1 - 0.20)
    if taxable <= 20000:
        return round(taxable * 0.20, 2)
    if taxable <= 50000:
        return round(taxable * 0.30 - 2000, 2)
    return round(taxable * 0.40 - 7000, 2)


class TaGuideCommission(models.Model):
    """导游佣金结算（BS-08）：两条路径——

    手工路径（无购物店）：补贴 allowance × 人工税率 tax_rate → 税额 → 税后净额。
    购物返佣路径（shop_partner_id 有值）：购物记录 → 购物协议返佣比例（含人均阶梯）
    → 佣金总额（经营收入）→ 司陪导协议分成 + 人均线奖金 → 个税预扣（劳务报酬 3 档；
    工资薪金并入月度综合所得、单笔不预扣）→ 税后净额冲抵借款（AC-18），余额支付。

    状态机（BS-08 §4.9 / AC-12）：待确认 → 已确认（会计，记确认人/时间，落个税记录）
    → 已结算（冲抵借款）。已取消用于退单重算（BS-08 §4.2 简化口径）。
    NFR-2：生成与结算均幂等。
    """
    _name = 'ta.guide.commission'
    _description = '导游佣金'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='佣金单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.guide.commission') or '/')
    date = fields.Date(required=True, default=fields.Date.context_today)
    guide_id = fields.Many2one('res.partner', string='导游', required=True, tracking=True)
    departure_id = fields.Many2one('ta.departure', string='发团计划', required=True)
    allowance = fields.Float(string='补贴/税前应发', required=True,
                             help='手工路径=补贴；购物返佣路径=导游税前分成+奖金（引擎生成）。')
    rule_note = fields.Char(string='规则参数', help='如：50元/天×3天+购物零返佣。')
    tax_rate = fields.Float(string='个税税率', default=0.0,
                            help='仅手工路径使用；购物返佣路径按劳务报酬/工资薪金规则自动计算。')

    # ---- BS-08 §4.9 计算结果字段（购物返佣路径，引擎生成）----
    shop_partner_id = fields.Many2one('res.partner', string='购物店', tracking=True)
    shop_amount = fields.Float(string='购物金额', digits=(15, 2),
                               help='该团该购物店已确认购物记录的金额合计。')
    guest_count = fields.Integer(string='客人数', help='团队客人数（BS-08 GuestCount 口径）。')
    per_capita = fields.Float(string='人均购物', digits=(15, 2),
                              help='= 购物金额 ÷ 团队客人数（BS-08 §4.9 阶梯匹配口径）。')
    agreement_id = fields.Many2one('ta.shop.agreement', string='购物协议', ondelete='restrict')
    commission_rate = fields.Float(string='返佣比例(%)', help='购物协议匹配的返佣比例（含阶梯）。')
    commission_total = fields.Float(string='佣金总额（经营收入）', digits=(15, 2),
                                    help='= 购物金额 × 返佣比例 [增值税暂行条例-经营收入]。')
    commission_tax = fields.Float(string='佣金增值税额', digits=(15, 2),
                                  help='佣金总额按公司税率价税分离的销项税额（参考值，凭证落地待批）。')
    guide_share_rate = fields.Float(string='导游分成比例(%)', help='司陪导协议分成比例。')
    guide_share_before_tax = fields.Float(string='导游税前分成', digits=(15, 2),
                                          help='[CAS 9-劳务成本] = 佣金总额 × 分成比例。')
    premium = fields.Float(string='导游奖金（税前）', digits=(15, 2),
                           help='人均线奖金 [个税法-劳务报酬]，合并计税。')
    guide_tax_type = fields.Selection([
        ('labor', '劳务报酬'),
        ('salary', '工资薪金'),
    ], string='税务类型', default='labor')
    guide_tax = fields.Float(string='代扣个税', digits=(15, 2),
                             help='购物返佣路径引擎计算的代扣个税；手工路径为空（用个税税率）。')
    company_retain = fields.Float(string='旅行社留存', digits=(15, 2),
                                  help='= 佣金总额 − 导游税前分成 − 奖金（BS-08 §4.9 步骤12）。')

    tax_amount = fields.Float(compute='_compute_amounts', store=True)
    net_amount = fields.Float(compute='_compute_amounts', store=True, tracking=True,
                              help='税后净额（BS-08 导游实发口径），冲抵借款用（AC-18）。')
    deducted_total = fields.Float(compute='_compute_amounts', store=True)
    payable_rest = fields.Float(compute='_compute_amounts', store=True)
    deduct_line_ids = fields.One2many('ta.guide.commission.deduct', 'commission_id', string='冲抵借款明细')
    tax_record_ids = fields.One2many('ta.guide.commission.tax', 'commission_id',
                                     string='个税代扣代缴记录')
    state = fields.Selection([
        ('draft', '待确认'),
        ('confirmed', '已确认'),
        ('settled', '已结算'),
        ('cancel', '已取消'),
    ], default='draft', required=True, tracking=True, copy=False)
    confirm_uid = fields.Many2one('res.users', string='确认人', readonly=True, copy=False)
    confirm_date = fields.Datetime(string='确认时间', readonly=True, copy=False)
    note = fields.Char()

    @api.depends('allowance', 'tax_rate', 'deduct_line_ids.net_deduct',
                 'shop_partner_id', 'guide_share_before_tax', 'premium', 'guide_tax')
    def _compute_amounts(self):
        for c in self:
            if c.shop_partner_id:
                c.tax_amount = c.guide_tax or 0.0
                c.net_amount = round((c.guide_share_before_tax or 0.0)
                                     + (c.premium or 0.0) - c.tax_amount, 2)
            else:
                c.tax_amount = round(c.allowance * c.tax_rate, 2)
                c.net_amount = c.allowance - c.tax_amount
            c.deducted_total = sum(c.deduct_line_ids.mapped('net_deduct'))
            c.payable_rest = c.net_amount - c.deducted_total

    # ---- BS-08 §4.9 计算引擎：按（发团计划 × 购物店）分组，幂等 upsert 草稿佣金单 ----
    def _upsert_from_shop_group(self, shop):
        """shop: ta.shop 单条（分组触发记录）。

        1. 汇总该团该店已确认购物金额；2. 查有效期内的购物协议 → 人均阶梯比例；
        3. 佣金总额 = 购物金额 × 比例；4. 查司陪导协议 → 分成 + 人均线奖金 + 税务类型；
        5. 劳务报酬按 3 档预扣个税（工资薪金单笔不预扣）；6. 旅行社留存 = 佣金总额 − 税前应发。
        已存在草稿单则更新（NFR-2 幂等），已确认/已结算单不动（改数走退单/红字流程）。
        """
        shop.ensure_one()
        Commission = self.env['ta.guide.commission']
        group = self.env['ta.shop'].search([
            ('departure_id', '=', shop.departure_id.id),
            ('shop_partner_id', '=', shop.shop_partner_id.id),
            ('state', '=', 'confirmed'),
        ])
        shop_amount = round(sum(group.mapped('total_amount')), 2)
        if shop_amount <= 0.01:
            return False
        agreement = self.env['ta.shop.agreement'].search([
            ('shop_partner_id', '=', shop.shop_partner_id.id),
            ('state', '=', 'active'),
            ('begin_date', '<=', shop.shop_date),
            ('end_date', '>=', shop.shop_date),
        ], limit=1, order='id desc')
        if not agreement:
            return False  # BS-08 §4.9：无协议不计佣
        team_heads = shop._team_heads()
        per_capita = round(shop_amount / team_heads, 2) if team_heads else 0.0
        rate = agreement._get_rate(per_capita, shop.shop_date)
        commission_total = round(shop_amount * rate / 100.0, 2)
        staff_agr = self.env['ta.staff.agreement'].search([
            ('staff_type', '=', 'guide'),
            ('staff_id', '=', shop.guide_id.id),
            ('state', '=', 'active'),
        ], limit=1, order='id desc')
        share_rate = staff_agr.share_rate or 0.0
        guide_share_before_tax = round(commission_total * share_rate / 100.0, 2)
        premium = round(staff_agr._get_premium(per_capita), 2) if staff_agr else 0.0
        tax_type = staff_agr.tax_type or 'labor'
        gross = round(guide_share_before_tax + premium, 2)
        if tax_type == 'labor':
            guide_tax = _calc_labor_tax(gross)
            tax_note = ''
        else:
            guide_tax = 0.0  # BS-08 §4.6：工资薪金并入月度综合所得计税，单笔不预扣
            tax_note = '（工资薪金并入月度综合所得计税，单笔不预扣）'
        icp = self.env['ir.config_parameter'].sudo()
        vat_rate = icp.get_float('ta_base.default_tax_rate', 0.0)
        commission_tax = round(commission_total * vat_rate / (1 + vat_rate), 2) if vat_rate else 0.0
        vals = {
            'guide_id': shop.guide_id.id,
            'departure_id': shop.departure_id.id,
            'date': shop.shop_date,
            'allowance': gross,
            'shop_partner_id': shop.shop_partner_id.id,
            'shop_amount': shop_amount,
            'guest_count': team_heads,
            'per_capita': per_capita,
            'agreement_id': agreement.id,
            'commission_rate': rate,
            'commission_total': commission_total,
            'commission_tax': commission_tax,
            'guide_share_rate': share_rate,
            'guide_share_before_tax': guide_share_before_tax,
            'premium': premium,
            'guide_tax_type': tax_type,
            'guide_tax': guide_tax,
            'company_retain': round(commission_total - gross, 2),
            'rule_note': (
                f"{agreement.name} 返佣 {rate}%×{shop_amount:.2f}={commission_total:.2f}；"
                f"导游分成 {share_rate}% + 奖金 {premium:.2f}{tax_note}"),
        }
        existing = Commission.search([
            ('departure_id', '=', shop.departure_id.id),
            ('shop_partner_id', '=', shop.shop_partner_id.id),
        ])
        draft = existing.filtered(lambda c: c.state == 'draft')
        if draft:
            draft[0].write(vals)
            return draft[0]
        if existing.filtered(lambda c: c.state in ('confirmed', 'settled')):
            return False
        return Commission.create(vals)

    # ---- 状态机（BS-08 步骤4/5、AC-12）----
    def action_confirm(self):
        """会计确认佣金：平衡校验 → 记确认人/时间 → 生成个税代扣记录（AC-10）。"""
        for c in self:
            if c.state != 'draft':
                raise UserError("只有待确认的佣金单可以确认。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("佣金确认需要会计权限。")
            if c.guide_id == self.env.user.partner_id:
                raise AccessError("确认人不能是导游本人。")
            if abs((c.tax_amount + c.net_amount) - c.allowance) > 0.01:
                raise UserError("税额与净额不平衡，请检查税率。")
            c.confirm_uid = self.env.user
            c.confirm_date = fields.Datetime.now()
            c._ensure_tax_record()
            c.state = 'confirmed'
            c.message_post(body=(
                f"佣金单已确认：佣金总额 {c.commission_total:.2f}，"
                f"导游税前 {c.allowance:.2f}，代扣个税 {c.tax_amount:.2f}，"
                f"税后净额 {c.net_amount:.2f}。"))
        return True

    def _ensure_tax_record(self):
        """个税代扣代缴记录（BS-08 §5.1 / AC-10）：确认时按单生成一行，按月汇总申报。"""
        for c in self:
            if c.tax_record_ids:
                continue
            staff_agr = self.env['ta.staff.agreement'].search([
                ('staff_type', '=', 'guide'),
                ('staff_id', '=', c.guide_id.id),
                ('state', '=', 'active'),
            ], limit=1, order='id desc')
            tax_type = (c.guide_tax_type if c.shop_partner_id
                        else (staff_agr.tax_type or c.guide_tax_type or 'labor'))
            self.env['ta.guide.commission.tax'].create({
                'commission_id': c.id,
                'staff_id': c.guide_id.id,
                'tax_type': tax_type,
                'id_number': (staff_agr.id_number or '') if staff_agr else '',
                'income_before_tax': c.allowance,
                'tax_amount': c.tax_amount,
                'net_pay': c.net_amount,
                'declare_month': fields.Date.context_today(c).isoformat()[:7],
            })

    def action_settle(self):
        """已确认佣金单：税后净额按最先到期借款优先冲抵；不足部分留余额支付（AC-18）。"""
        for c in self:
            if c.state != 'confirmed':
                raise UserError("只有已确认的佣金单可以结算冲抵借款（先确认，AC-12）。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("佣金结算需要会计权限。")
            if abs((c.tax_amount + c.net_amount) - c.allowance) > 0.01:
                raise UserError("税额与净额不平衡，请检查税率。")
            available = c.net_amount
            loans = self.env['ta.guide.loan'].search([
                ('guide_id', '=', c.guide_id.id),
                ('state', '=', 'paid'),
                ('outstanding', '>', 0.01),
                ('company_id', '=', c.company_id.id),
            ], order='due_date asc, date asc')
            for loan in loans:
                if available <= 0.01:
                    break
                take = min(available, loan.outstanding)
                self.env['ta.guide.commission.deduct'].create({
                    'commission_id': c.id, 'loan_id': loan.id, 'net_deduct': take})
                available = round(available - take, 2)
                if loan.outstanding <= 0.01:
                    loan.state = 'settled'
                    loan.message_post(body=f"借款 {loan.name} 已由佣金单 {c.name} 结清。")
            c.state = 'settled'
            c.message_post(body=(
                f"税后净额 {c.net_amount:.2f} 已冲抵借款 {c.deducted_total:.2f}，"
                f"余额支付 {c.payable_rest:.2f}。个税 {c.tax_amount:.2f} 于次月 15 日前申报缴纳。"))
        return True

    def action_cancel(self):
        for c in self:
            if c.state != 'draft':
                raise UserError("只有待确认的佣金单可以取消。")
            c.state = 'cancel'


class TaGuideCommissionDeduct(models.Model):
    _name = 'ta.guide.commission.deduct'
    _description = '佣金冲抵借款行'
    _inherit = ['ta.mixin']

    commission_id = fields.Many2one('ta.guide.commission', ondelete='cascade', required=True)
    loan_id = fields.Many2one('ta.guide.loan', string='借款单', ondelete='restrict', required=True)
    net_deduct = fields.Float(string='冲抵金额（税后净额）', required=True)

    _deduct_positive = models.Constraint(
        'check(net_deduct > 0)', '冲抵金额必须为正。')


class TaGuideCommissionTax(models.Model):
    """个税代扣代缴记录（BS-08 §5.1 tour.commission.tax.record / AC-10）：
    佣金确认时自动生成，按月汇总申报，申报状态可流转。"""
    _name = 'ta.guide.commission.tax'
    _description = '佣金个税代扣代缴记录'
    _inherit = ['ta.mixin']
    _order = 'declare_month desc, id desc'

    commission_id = fields.Many2one('ta.guide.commission', ondelete='cascade', required=True)
    staff_id = fields.Many2one('res.partner', string='人员', required=True)
    staff_name = fields.Char(related='staff_id.name', string='人员姓名')
    tax_type = fields.Selection([
        ('labor', '劳务报酬'),
        ('salary', '工资薪金'),
    ], string='税务类型', required=True)
    id_number = fields.Char(string='身份证号（脱敏）',
                            help='[个税法-代扣代缴] 仅存脱敏形式。')
    income_before_tax = fields.Float(string='税前收入', digits=(15, 2), required=True)
    tax_amount = fields.Float(string='代扣税额', digits=(15, 2), required=True)
    net_pay = fields.Float(string='实发金额', digits=(15, 2), required=True)
    declare_month = fields.Char(string='申报月份', size=7, required=True,
                                help='YYYY-MM，按月汇总申报 [个税法-申报]。')
    declare_state = fields.Selection([
        ('undeclared', '未申报'),
        ('declared', '已申报'),
        ('paid', '已缴纳'),
    ], string='申报状态', default='undeclared', required=True)
    declare_date = fields.Date(string='申报日期')

    def action_declare(self):
        for r in self:
            if r.declare_state != 'undeclared':
                raise UserError("只有未申报记录可以标记申报。")
            r.declare_state = 'declared'
            r.declare_date = fields.Date.context_today(r)
