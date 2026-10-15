# -*- coding: utf-8 -*-
import decimal

from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError, ValidationError


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


def _round_amount(value, round_way='half_up', decimal_places=2):
    """金额/人均取整（BS-08 §4.8）：half_up 四舍五入（沿用旧口径 round()）、
    up 向上取整、down 向下取整。"""
    if round_way == 'half_up':
        return round(value, decimal_places)
    quant = decimal.Decimal('1e-%d' % decimal_places)
    rounding = decimal.ROUND_UP if round_way == 'up' else decimal.ROUND_DOWN
    return float(decimal.Decimal(str(value)).quantize(quant, rounding=rounding))


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
    staff_line_ids = fields.One2many('ta.commission.staff', 'commission_id', string='分成明细',
                                     help='多层分成行（P1-2 / BS-08 §3.2）：导游/司机/陪同各自'
                                          '税前分成、奖金、代扣个税与实发。')
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
    move_id = fields.Many2one('account.move', string='确认凭证', readonly=True, copy=False,
                              help='确认时生成的会计凭证（BS-08 §4.10.1/4.10.2，含销项税 AC-19）。')
    settle_move_id = fields.Many2one('account.move', string='冲抵凭证', readonly=True, copy=False,
                                     help='结算时生成的借款冲抵凭证（BS-08 §4.10.4：借 2241 / 贷 1221）。')
    note = fields.Char()

    @api.depends('allowance', 'tax_rate', 'deduct_line_ids.net_deduct',
                 'shop_partner_id', 'guide_share_before_tax', 'premium', 'guide_tax',
                 'staff_line_ids.tax_amount', 'staff_line_ids.net_pay',
                 'staff_line_ids.share_before_tax', 'staff_line_ids.premium')
    def _compute_amounts(self):
        for c in self:
            if c.shop_partner_id:
                if c.staff_line_ids:
                    # P1-2 多层分成：主单税额/净额 = Σ各分成行（BS-08 §3.2）
                    c.tax_amount = round(sum(c.staff_line_ids.mapped('tax_amount')), 2)
                    c.net_amount = round(sum(c.staff_line_ids.mapped('net_pay')), 2)
                else:
                    # 无分成行（旧数据/无协议）：退回原单导游口径，向后兼容
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
        3. 佣金总额 = 购物金额 × 比例；4. 人均计算按生效 ta.per.capita.calc
        （简单/加权/分段，取整方式与小数位数可配，§4.8，无配置=旧口径）；
        5. 人均线（§4.7）仅考核导游：三档比例命中导游行，空档回退协议 share_rate；
        6. 多层分成（§3.2）：导游（shop.guide_id）+ 发团司机/陪同各自的生效
        ta.staff.agreement 生成 ta.commission.staff 分成行；奖金规则按人均命中
        （司机/陪同协议配置了奖金规则同样生效）；劳务报酬按 3 档预扣个税
        （工资薪金单笔不预扣）；7. 旅行社留存 = 佣金总额 − Σ各行税前应发。
        已存在草稿单则更新（NFR-2 幂等），已确认/已结算单不动（改数走退单/红字流程）。
        """
        shop.ensure_one()
        Commission = self.env['ta.guide.commission']
        group = self.env['ta.shop'].search([
            ('departure_id', '=', shop.departure_id.id),
            ('shop_partner_id', '=', shop.shop_partner_id.id),
            ('state', '=', 'confirmed'),
        ])
        # P0-4（BS-08 §4.2）：有效金额 = 总金额 − 已确认退单（退单红字口径）
        shop_amount = round(sum(
            g.total_amount - g.return_amount_total for g in group), 2)
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
        departure = shop.departure_id
        team_heads = shop._team_heads()
        # ---- 人均算法（BS-08 §4.8 / P1-3）：无生效配置时与旧口径完全一致 ----
        calc = self.env['ta.per.capita.calc']._resolve_calc(
            departure.route_id.id, shop.shop_partner_id.id)
        if calc:
            calc_mode = 'simple' if calc.calc_mode == 'segment' else calc.calc_mode
            round_way, decimals = calc.round_way, calc.decimal_places
            calc_desc = calc.name or ''
        else:
            calc_mode, round_way, decimals = 'simple', 'half_up', 2
            calc_desc = ''
        if calc_mode == 'weighted':
            heads = shop._team_heads_weighted()
        else:
            heads = float(team_heads)
        per_capita = _round_amount(shop_amount / heads, round_way, decimals) if heads else 0.0
        rate = agreement._get_rate(per_capita, shop.shop_date)
        commission_total = round(shop_amount * rate / 100.0, 2)
        # ---- 司陪导协议（§4.6）：每类人员取各自最新生效协议 ----
        Agreement = self.env['ta.staff.agreement']

        def _agreement(staff_type, partner):
            if not partner:
                return Agreement.browse()
            return Agreement.search([
                ('staff_type', '=', staff_type),
                ('staff_id', '=', partner.id),
                ('state', '=', 'active'),
            ], limit=1, order='id desc')

        guide_agr = _agreement('guide', shop.guide_id)
        driver_agr = _agreement('driver', departure.driver_id)
        escort_agr = _agreement('escort', departure.escort_id)
        # ---- 人均线（BS-08 §4.7 / P1-3）：仅导游考核，三档比例，空档回退协议 ----
        guide_rate = None
        pcl_note = ''
        pcl = self.env['ta.per.capita.line']._match_line(
            departure.route_id.id, shop.shop_partner_id.id)
        if pcl and guide_agr:
            tier_rate, tier_name = pcl._tier_rate(per_capita)
            if pcl.line_id:
                where = f"线路[{pcl.line_id.name}]"
            elif pcl.shop_id:
                where = f"购物店[{pcl.shop_id.name}]"
            else:
                where = "全局"
            if tier_rate:
                guide_rate = tier_rate
                pcl_note = f"人均线({where})：{tier_name}档 {tier_rate}%"
            else:
                pcl_note = f"人均线({where})：{tier_name}档未配置比例，回退司陪导协议"
        # ---- 多层分成行（§3.2）：每个有生效协议的人员一行 ----
        STAFF_LABEL = {'guide': '导游', 'driver': '司机', 'escort': '陪同'}
        rows_vals = []
        guide_row = None
        for staff_type, partner, agr in (
                ('guide', shop.guide_id, guide_agr),
                ('driver', departure.driver_id, driver_agr),
                ('escort', departure.escort_id, escort_agr)):
            if not agr:
                continue
            if staff_type == 'guide' and guide_rate is not None:
                share_rate = guide_rate
            else:
                share_rate = agr.share_rate or 0.0
            share_bt = round(commission_total * share_rate / 100.0, 2)
            premium = round(agr._get_premium(per_capita), 2)
            gross = round(share_bt + premium, 2)
            tax_type = agr.tax_type or 'labor'
            tax = _calc_labor_tax(gross) if tax_type == 'labor' else 0.0
            row = {
                'staff_type': staff_type,
                'staff_id': partner.id,
                'share_rate': share_rate,
                'share_before_tax': share_bt,
                'premium': premium,
                'tax_type': tax_type,
                'tax_amount': tax,
                'net_pay': round(gross - tax, 2),
            }
            rows_vals.append(row)
            if staff_type == 'guide':
                guide_row = row
        # ---- 主单 guide_* 兼容字段：= 导游行；无导游协议时沿用旧口径（全 0/无奖金）----
        if guide_row:
            g_rate = guide_row['share_rate']
            g_share = guide_row['share_before_tax']
            g_premium = guide_row['premium']
            g_tax_type = guide_row['tax_type']
            g_tax = guide_row['tax_amount']
        else:
            g_rate = guide_agr.share_rate or 0.0 if guide_agr else 0.0
            g_share = round(commission_total * g_rate / 100.0, 2)
            g_premium = round(guide_agr._get_premium(per_capita), 2) if guide_agr else 0.0
            g_gross = round(g_share + g_premium, 2)
            g_tax_type = (guide_agr.tax_type or 'labor') if guide_agr else 'labor'
            g_tax = _calc_labor_tax(g_gross) if g_tax_type == 'labor' else 0.0
        # §3.2：主单税前应发 = Σ各分成行（分成+奖金）；无行时回退导游旧口径
        allowance = (round(sum(r['share_before_tax'] + r['premium'] for r in rows_vals), 2)
                     if rows_vals else round(g_share + g_premium, 2))
        tax_note = ('（工资薪金并入月度综合所得计税，单笔不预扣）'
                    if any(r['tax_type'] == 'salary' for r in rows_vals) else '')
        icp = self.env['ir.config_parameter'].sudo()
        vat_rate = icp.get_float('ta_base.default_tax_rate', 0.0)
        commission_tax = round(commission_total * vat_rate / (1 + vat_rate), 2) if vat_rate else 0.0
        parts = [f"{agreement.name} 返佣 {rate}%×{shop_amount:.2f}={commission_total:.2f}"]
        if calc_desc:
            parts.append(f"人均算法：{calc_desc}")
        if pcl_note:
            parts.append(pcl_note)
        staff_parts = []
        for r in rows_vals:
            staff_parts.append(
                f"{STAFF_LABEL[r['staff_type']]}分成 {r['share_rate']}% + 奖金 {r['premium']:.2f}")
        if staff_parts:
            parts.append("；".join(staff_parts))
        elif guide_agr:
            parts.append(f"导游分成 {g_rate}% + 奖金 {g_premium:.2f}")
        if tax_note:
            parts.append(tax_note)
        vals = {
            'guide_id': shop.guide_id.id,
            'departure_id': shop.departure_id.id,
            'date': shop.shop_date,
            'allowance': allowance,
            'shop_partner_id': shop.shop_partner_id.id,
            'shop_amount': shop_amount,
            'guest_count': team_heads,
            'per_capita': per_capita,
            'agreement_id': agreement.id,
            'commission_rate': rate,
            'commission_total': commission_total,
            'commission_tax': commission_tax,
            'guide_share_rate': g_rate,
            'guide_share_before_tax': g_share,
            'premium': g_premium,
            'guide_tax_type': g_tax_type,
            'guide_tax': g_tax,
            'company_retain': round(commission_total - allowance, 2),
            'rule_note': "；".join(parts),
            'staff_line_ids': [(5, 0, 0)] + [(0, 0, r) for r in rows_vals],
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
        """会计确认佣金：平衡校验 → 记确认人/时间 → 生成确认凭证（§4.10.1/4.10.2，
        含销项税 AC-19）→ 生成个税代扣记录（AC-10）。凭证仅确认时生成一次（NFR-2）。"""
        for c in self:
            if c.state != 'draft':
                raise UserError("只有待确认的佣金单可以确认。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("佣金确认需要会计权限。")
            if c.guide_id == self.env.user.partner_id:
                raise AccessError("确认人不能是导游本人。")
            if abs((c.tax_amount + c.net_amount) - c.allowance) > 0.01:
                raise UserError("税额与净额不平衡，请检查税率。")
            if c.shop_partner_id:
                c._ta_apply_tax_deduction()
            c.confirm_uid = self.env.user
            c.confirm_date = fields.Datetime.now()
            c.move_id = c._create_confirm_move()
            c._ensure_tax_record()
            c.state = 'confirmed'
            c.message_post(body=(
                f"佣金单已确认：佣金总额 {c.commission_total:.2f}，"
                f"导游税前 {c.allowance:.2f}，代扣个税 {c.tax_amount:.2f}，"
                f"税后净额 {c.net_amount:.2f}。确认凭证已生成。"))
        return True

    def _ta_apply_tax_deduction(self):
        """P0-4（BS-08 §4.2）：退单个税抵扣——同人 pending 抵扣记录按金额顺序
        整条冲减本次分成行代扣个税（下限 0，凭证 222102 少贷、净额多付一致联动）；
        用不完的记录留 pending（可申请退税）。改写须先于 _create_confirm_move。"""
        self.ensure_one()
        Deduct = self.env['ta.guide.commission.tax.deduct']
        for row in self.staff_line_ids:
            if row.tax_amount <= 0.005:
                continue
            pending = Deduct.search([
                ('staff_id', '=', row.staff_id.id),
                ('state', '=', 'pending'),
            ], order='id asc')
            reduction = 0.0
            for d in pending:
                if d.amount > row.tax_amount - reduction + 0.005:
                    break  # 单条超出本次税额 → 整条留 pending
                reduction = round(reduction + d.amount, 2)
                d.state = 'used'
            if reduction > 0.005:
                old_tax = row.tax_amount
                new_tax = round(old_tax - reduction, 2)
                gross = round(row.share_before_tax + row.premium, 2)
                row.write({'tax_amount': new_tax,
                           'net_pay': round(gross - new_tax, 2)})
                self.message_post(body=(
                    f"退单个税抵扣：{row.staff_id.name} 本次代扣个税由 {old_tax:.2f}"
                    f" 抵减 {reduction:.2f} 至 {new_tax:.2f}（BS-08 §4.2）。"))

    def _ensure_tax_record(self):
        """个税代扣代缴记录（BS-08 §5.1 / AC-10）：确认时按分成行逐人生成（P1-2），
        按月汇总申报；无分成行时维持原单导游一条记录（向后兼容旧数据/手工路径）。"""
        for c in self:
            if c.tax_record_ids:
                continue
            month = fields.Date.context_today(c).isoformat()[:7]
            rows = c.staff_line_ids
            if rows:
                for row in rows:
                    staff_agr = self.env['ta.staff.agreement'].search([
                        ('staff_type', '=', row.staff_type),
                        ('staff_id', '=', row.staff_id.id),
                        ('state', '=', 'active'),
                    ], limit=1, order='id desc')
                    self.env['ta.guide.commission.tax'].create({
                        'commission_id': c.id,
                        'staff_id': row.staff_id.id,
                        'tax_type': row.tax_type,
                        'id_number': (staff_agr.id_number or '') if staff_agr else '',
                        'income_before_tax': round(row.share_before_tax + row.premium, 2),
                        'tax_amount': row.tax_amount,
                        'net_pay': row.net_pay,
                        'declare_month': month,
                    })
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
                'declare_month': month,
            })

    # ---- BS-08 §4.10 会计凭证（P0-1 会计分录落地 + P0-2/AC-19 销项税）----
    def _get_commission_account(self, code, name, account_type, keywords=None, **extra):
        """§4.10 科目解析（按 code+company，带游标级缓存，命中校验 exists()）：
        ① 同 code 前缀 + 名称关键词语义匹配 → 直接复用既有科目；
        ② 精确 code 匹配 → 复用；
        ③ 都没有 → sudo 幂等补建（与 noupdate=1 data XML 的 SUPERUSER 载入等价）；
        ④ 创建受限/失败 → 中文 UserError 提示会计补科目，绝不静默跳过。

        不采用 data XML 的理由：
        - 本版 Odoo 20 的 account.code 是公司级计算字段（code_store jsonb），
          XML 建科目依赖公司上下文，跨公司（ta.mixin SaaS 预留）不可控；
        - 科目须按佣金单 company_id 运行时解析，XML 只能钉死公司 id=1；
        - tour20 已有前序批次存量科目（1221/2241），"存在即复用"XML 表达不了；
        - 影子库反复 -u 升级时动态方式天然幂等，无 XML 冲突风险。
        """
        self.ensure_one()
        company = self.company_id
        # 游标级缓存（每请求/每事务独立；命中时校验 exists()，防测试 savepoint
        # 回滚后的过期 id —— 环境级缓存会因 with_user 复用同一 env 对象而跨 savepoint 泄漏）
        cache = getattr(self.env.cr, '_ta_commission_account_cache', None)
        if cache is None:
            cache = self.env.cr._ta_commission_account_cache = {}
        key = (company.id, code)
        account = cache.get(key)
        if account and account.exists():
            return account
        Account = self.env['account.account'].with_company(company)
        base = [('company_ids', 'in', company.ids)]
        prefix = code[:4]
        for kw in (keywords or [name]):
            hit = Account.search(
                base + [('code', '=like', f'{prefix}%'), ('name', 'ilike', kw)], limit=1)
            if hit:
                cache[key] = hit
                return hit
        hit = Account.search(base + [('code', '=', code)], limit=1)
        if hit:
            cache[key] = hit
            return hit
        vals = {'code': code, 'name': name, 'account_type': account_type,
                'company_ids': [(6, 0, company.ids)]}
        vals.update(extra)
        try:
            account = Account.sudo().create(vals)
        except (AccessError, ValidationError) as exc:
            msg = exc.args[0] if exc.args else exc
            raise UserError(
                f"缺少会计科目 {code} {name}（公司：{company.name}），自动创建失败：{msg}。"
                f"请会计在会计科目表中补建该科目后重试。") from exc
        cache[key] = account
        return account

    def _get_general_journal(self):
        journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError("当前公司没有杂项日记账（general），无法生成佣金凭证。")
        return journal

    def _create_confirm_move(self):
        """确认凭证（BS-08 §4.10.1 佣金收入 + §4.10.2 导游分成应付，两笔分录合一）：

        购物返佣路径（shop_partner_id 有值）：前 3 行固定（1222/6051/222101 销项税 AC-19），
        6407 导服成本 / 2241 应付分成 / 222102 代扣个税按分成行拆行（P1-2：每人三行，
        partner_id=该人员，借贷合计不变，共 3+3×人数 行）；无分成行退回原单导游三行。
        手工路径（无 shop_partner_id）3 行：
          借 6407 = allowance；贷 2241 = net_amount；贷 222102 = tax_amount。
        税率未配置（commission_tax=0）时销项行为 0、收入行=全额，仍保持平衡（NFR-1）。
        """
        self.ensure_one()
        lines = []
        if self.shop_partner_id:
            acc_receivable = self._get_commission_account(
                '1222', '其他应收款-购物佣金', 'asset_receivable', ['购物佣金'], reconcile=True)
            acc_income = self._get_commission_account(
                '6051', '其他业务收入-佣金', 'income_other', ['其他业务收入', '佣金'])
            acc_vat = self._get_commission_account(
                '222101', '应交税费-应交增值税(销项税额)', 'liability_payable',
                ['销项', '增值税'])
            income = round(self.commission_total - self.commission_tax, 2)
            lines += [
                (0, 0, {'name': f"佣金 {self.name} 购物店应收",
                        'partner_id': self.shop_partner_id.id,
                        'account_id': acc_receivable.id, 'debit': self.commission_total}),
                (0, 0, {'name': f"佣金收入 {self.name}",
                        'account_id': acc_income.id, 'credit': income}),
                (0, 0, {'name': f"销项税额 {self.name}",
                        'account_id': acc_vat.id, 'credit': self.commission_tax}),
            ]
        acc_cost = self._get_commission_account(
            '6407', '主营业务成本-导服', 'expense', ['导服', '劳务成本'])
        acc_payable = self._get_commission_account(
            '2241', '其他应付款-导游分成', 'liability_payable',
            ['导游分成', '其他应付款'], reconcile=True)
        acc_wh_tax = self._get_commission_account(
            '222102', '应交税费-代扣个税', 'liability_payable', ['个税', '代扣'])
        rows = self.staff_line_ids
        if rows:
            # P1-2：6407/2241/222102 按分成行拆行，partner_id=该人员
            for row in rows:
                gross = round(row.share_before_tax + row.premium, 2)
                pname = row.staff_id.name or ''
                lines += [
                    (0, 0, {'name': f"导服成本 {self.name} {pname}",
                            'partner_id': row.staff_id.id,
                            'account_id': acc_cost.id, 'debit': gross}),
                    (0, 0, {'name': f"应付分成 {self.name} {pname}",
                            'partner_id': row.staff_id.id,
                            'account_id': acc_payable.id, 'credit': row.net_pay}),
                    (0, 0, {'name': f"代扣个税 {self.name} {pname}",
                            'partner_id': row.staff_id.id,
                            'account_id': acc_wh_tax.id, 'credit': row.tax_amount}),
                ]
        else:
            lines += [
                (0, 0, {'name': f"导服成本 {self.name}", 'partner_id': self.guide_id.id,
                        'account_id': acc_cost.id, 'debit': self.allowance}),
                (0, 0, {'name': f"应付导游分成 {self.name}", 'partner_id': self.guide_id.id,
                        'account_id': acc_payable.id, 'credit': self.net_amount}),
                (0, 0, {'name': f"代扣个税 {self.name}", 'partner_id': self.guide_id.id,
                        'account_id': acc_wh_tax.id, 'credit': self.tax_amount}),
            ]
        debit_total = sum(line[2].get('debit', 0.0) for line in lines)
        credit_total = sum(line[2].get('credit', 0.0) for line in lines)
        if abs(debit_total - credit_total) > 0.01:
            raise UserError("佣金确认凭证借贷不平衡，无法生成凭证（NFR-1）。")
        move = self.env['account.move'].create({
            'journal_id': self._get_general_journal().id,
            'date': self.date,
            'ref': f"佣金确认 {self.name} / {self.guide_id.name}",
            'line_ids': lines,
        })
        move.action_post()
        return move

    def _create_settle_move(self):
        """借款冲抵凭证（BS-08 §4.10.4 / AC-18）：借 2241 其他应付款-导游分成 /
        贷 1221 其他应收款-导游借款，按冲抵明细一对一生成（借贷恒平衡）。

        前提：借款发放（ta.guide.loan.action_pay）已生成 1221 借方凭证，
        贷方科目取自借款发放凭证的借方行，保证精确对冲同一科目。
        """
        self.ensure_one()
        acc_payable = self._get_commission_account(
            '2241', '其他应付款-导游分成', 'liability_payable',
            ['导游分成', '其他应付款'], reconcile=True)
        lines = []
        for dl in self.deduct_line_ids:
            acc_loan = dl.loan_id._resolve_loan_account()
            lines += [
                (0, 0, {'name': f"冲抵分成 {self.name} / {dl.loan_id.name}",
                        'partner_id': self.guide_id.id,
                        'account_id': acc_payable.id, 'debit': dl.net_deduct}),
                (0, 0, {'name': f"冲抵借款 {dl.loan_id.name}",
                        'partner_id': self.guide_id.id,
                        'account_id': acc_loan.id, 'credit': dl.net_deduct}),
            ]
        debit_total = sum(line[2].get('debit', 0.0) for line in lines)
        credit_total = sum(line[2].get('credit', 0.0) for line in lines)
        if abs(debit_total - credit_total) > 0.01:
            raise UserError("借款冲抵凭证借贷不平衡，无法生成凭证（NFR-1）。")
        move = self.env['account.move'].create({
            'journal_id': self._get_general_journal().id,
            'date': self.date,
            'ref': f"佣金冲抵借款 {self.name} / {self.guide_id.name}",
            'line_ids': lines,
        })
        move.action_post()
        return move

    def action_settle(self):
        """已确认佣金单：税后净额按最先到期借款优先冲抵（AC-18），并生成
        4.10.4 冲抵凭证（借 2241 导游分成 / 贷 1221 导游借款）；不足部分留余额支付。"""
        for c in self:
            if c.state != 'confirmed':
                raise UserError("只有已确认的佣金单可以结算冲抵借款（先确认，AC-12）。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("佣金结算需要会计权限。")
            if abs((c.tax_amount + c.net_amount) - c.allowance) > 0.01:
                raise UserError("税额与净额不平衡，请检查税率。")
            # 多层分成口径（P1-2）：只有导游行的实发才能冲导游借款；
            # 司机/陪同实发另行支付（BS-08 §4.10.4），不得挪用冲抵。
            rows = c.staff_line_ids
            if rows:
                guide_net = round(sum(rows.filtered(
                    lambda r: r.staff_type == 'guide').mapped('net_pay')), 2)
            else:
                guide_net = c.net_amount
            available = guide_net
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
            total_deduct = sum(c.deduct_line_ids.mapped('net_deduct'))
            if total_deduct > 0.01:
                c.settle_move_id = c._create_settle_move()
            c.state = 'settled'
            staff_note = ''
            if rows:
                staff_rest = round(sum(rows.filtered(
                    lambda r: r.staff_type != 'guide').mapped('net_pay')), 2)
                if staff_rest > 0.01:
                    staff_note = f"司机/陪同实发 {staff_rest:.2f} 另行走支付流程。"
            c.message_post(body=(
                f"导游税后净额 {guide_net:.2f} 已冲抵借款 {total_deduct:.2f}，"
                f"余额支付 {c.payable_rest:.2f}。个税 {c.tax_amount:.2f} 于次月 15 日前申报缴纳。"
                f"{staff_note}冲抵凭证已生成。"))
        return True

    def action_cancel(self):
        for c in self:
            if c.state != 'draft':
                raise UserError("只有待确认的佣金单可以取消。")
            c.state = 'cancel'


class TaCommissionStaff(models.Model):
    """佣金分成行（P1-2 / BS-08 §3.2）：导游/司机/陪同各自的分成结果。

    引擎按每个有生效 ta.staff.agreement 的人员生成一行：
    share_before_tax = 佣金总额 × share_rate%；premium 用协议奖金规则按人均命中
    （司机/陪同协议配置了奖金规则同样生效）；labor 按劳务报酬 3 档预扣、salary 单笔不预扣；
    net_pay = 税前分成 + 奖金 − 代扣个税。主单 allowance/tax_amount/net_amount 由各行汇总。
    """
    _name = 'ta.commission.staff'
    _description = '佣金分成行'
    _inherit = ['ta.mixin']
    _order = 'staff_type, id'

    commission_id = fields.Many2one('ta.guide.commission', string='佣金单',
                                    ondelete='cascade', required=True, index=True)
    staff_type = fields.Selection([
        ('guide', '导游'),
        ('driver', '司机'),
        ('escort', '陪同'),
    ], string='人员类型', required=True)
    staff_id = fields.Many2one('res.partner', string='人员', required=True)
    staff_name = fields.Char(related='staff_id.name', string='人员姓名')
    share_rate = fields.Float(string='分成比例(%)', digits=(5, 2),
                              help='导游行可被人均线档位比例覆盖（§4.7）；司机/陪同用协议比例。')
    share_before_tax = fields.Float(string='税前分成', digits=(15, 2), required=True,
                                    help='= 佣金总额 × 分成比例（BS-08 §3.2）。')
    premium = fields.Float(string='奖金', digits=(15, 2), default=0.0,
                           help='协议奖金规则按人均命中金额，合并计税（BS-08 §4.6）。')
    tax_type = fields.Selection([
        ('labor', '劳务报酬'),
        ('salary', '工资薪金'),
    ], string='税务类型', required=True, default='labor')
    tax_amount = fields.Float(string='代扣个税', digits=(15, 2), default=0.0)
    net_pay = fields.Float(string='实发', digits=(15, 2), required=True,
                           help='= 税前分成 + 奖金 − 代扣个税（BS-08 导游实发口径）。')


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
