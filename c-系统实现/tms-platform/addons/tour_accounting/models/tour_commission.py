# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourCommission(models.Model):
    _name = 'tour.commission'
    _description = '佣金（含个税代扣）'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.accounting.mixin']
    _order = 'id desc'

    name = fields.Char('佣金编号', required=True, copy=False, default='新建')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.commission') or '新建'
        return super().create(vals_list)

    # === 佣金来源 ===
    plan_id = fields.Many2one('tour.plan', string='团队订单', required=True, index=True,
                              ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    shop_id = fields.Many2one('res.partner', string='购物店', index=True,
                              domain=[('sup_type', '=', 'shop')])
    shop_name = fields.Char('购物店名称')
    agreement_id = fields.Many2one('tour.shop.agreement', string='购物协议',
                                   help='返佣比例来源 [印花税法-合同]')
    commission_rate = fields.Float('返佣比例(%)', digits=(5, 2))
    shop_amount = fields.Float('购物金额', digits=(16, 2))
    commission_total = fields.Float('佣金总额(经营收入)', digits=(16, 2),
                                    help='购物店返佣，属经营收入，不可冲减成本 [增值税暂行条例]')

    # === 导游分成 ===
    guide_id = fields.Many2one('tour.guide', string='导游', index=True)
    guide_share_rate = fields.Float('导游分成比例(%)', digits=(5, 2))
    guide_share_before_tax = fields.Float('导游税前分成', digits=(16, 2))
    premium = fields.Float('导游奖金(税前)', digits=(16, 2),
                           help='人均线奖金，合并计入当次个税 [个税法-劳务报酬]')

    # === 个税代扣 ===
    guide_tax_type = fields.Selection([
        ('labor', '劳务报酬'),
        ('salary', '工资薪金'),
    ], string='税务类型', default='labor',
       help='劳务报酬（默认，20%-40% 累进）；工资薪金待后续实现 [CAS 9 / 个税法]')
    guide_tax = fields.Float('代扣个税', digits=(16, 2), compute='_compute_tax', store=True,
                             help='劳务报酬预扣个税 [个税法-代扣代缴]')
    guide_net_pay = fields.Float('导游实发', digits=(16, 2), compute='_compute_tax', store=True,
                                 help='= 税前分成+奖金 - 代扣个税')
    company_retain = fields.Float('旅行社留存', digits=(16, 2), compute='_compute_tax',
                                  store=True, help='= 佣金总额 - 导游税前分成 - 奖金')

    # === 状态/归属 ===
    state = fields.Selection([
        ('draft', '待确认'),
        ('confirmed', '已确认'),
        ('received', '已收款'),
        ('paid', '已发放'),
    ], string='状态', default='draft', required=True, index=True)
    confirm_uid = fields.Many2one('res.users', string='确认人')
    confirm_date = fields.Datetime('确认时间')
    pay_uid = fields.Many2one('res.users', string='发放人')
    pay_date = fields.Datetime('发放时间')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    # === 会计凭证回链 ===
    move_id = fields.Many2one('account.move', string='计提凭证', copy=False,
                              ondelete='restrict', index=True,
                              help='确认时生成的计提凭证（借导服成本/贷应付导游+代扣个税）')
    move_state = fields.Selection(related='move_id.state', string='凭证状态')
    pay_move_id = fields.Many2one('account.move', string='发放凭证', copy=False,
                                  ondelete='restrict', index=True,
                                  help='发放时生成的付款凭证（借应付导游/贷资金）[Phase 2 深化]')
    pay_move_state = fields.Selection(related='pay_move_id.state', string='发放凭证状态')
    pay_journal_id = fields.Many2one('account.journal', string='付款日记账',
                                     help='发放导游分成落账日记账；留空按银行存款日记账（bank）路由')

    @api.depends('commission_total', 'guide_share_before_tax', 'premium', 'guide_tax_type')
    def _compute_tax(self):
        for rec in self:
            before_tax = (rec.guide_share_before_tax or 0.0) + (rec.premium or 0.0)
            if rec.guide_tax_type == 'labor':
                rec.guide_tax = self._calc_labor_tax(before_tax)
            else:
                # 工资薪金代扣（3%-45% 累进）待后续实现
                rec.guide_tax = 0.0
            rec.guide_net_pay = before_tax - rec.guide_tax
            rec.company_retain = (rec.commission_total or 0.0) - before_tax

    @staticmethod
    def _calc_labor_tax(amount):
        """劳务报酬预扣个税 [个税法-劳务报酬]
        - ≤ 800：不预扣
        - 800 < x ≤ 4000：预扣 = (x - 800) × 20%
        - x > 4000：预扣 = x × (1-20%) × 税率 - 速算扣除数
        """
        amount = amount or 0.0
        if amount <= 800:
            return 0.0
        if amount <= 4000:
            return round((amount - 800) * 0.20, 2)
        taxable = amount * 0.80
        if taxable <= 20000:
            return round(taxable * 0.20, 2)
        if taxable <= 50000:
            return round(taxable * 0.30 - 2000, 2)
        return round(taxable * 0.40 - 7000, 2)

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.write({
                'state': 'confirmed',
                'confirm_uid': self.env.user.id,
                'confirm_date': fields.Datetime.now(),
            })
            if not rec.move_id:
                rec.move_id = rec._generate_accrual_move()

    def _generate_accrual_move(self):
        """生成佣金计提凭证 [BS-10 §7.4.2]：
        借 6401.07 成本—导服费 = 税前分成 + 奖金
            贷 2241.02 其他应付款—导游分成 = 实发
            贷 2221.05 应交税费—应交个人所得税 = 代扣个税
        """
        self.ensure_one()
        before_tax = (self.guide_share_before_tax or 0.0) + (self.premium or 0.0)
        net_pay = self.guide_net_pay or 0.0
        tax = self.guide_tax or 0.0
        if before_tax <= 0 and tax <= 0:
            raise ValidationError('佣金计提金额为 0，无法生成凭证')

        cost_acc = self._tour_get_account(self.ACCOUNT_COST_GUIDE)
        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_GUIDE)
        tax_acc = self._tour_get_account(self.ACCOUNT_TAX_IIT)
        journal = self._tour_get_journal('general')
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self.guide_id.partner_id.id if self.guide_id and self.guide_id.partner_id else None
        narration = '%s / %s / 佣金计提' % (
            self.plan_code or '-', self.guide_id.name if self.guide_id else '未关联导游')

        lines = [{
            'account_id': cost_acc.id,
            'debit': before_tax,
            'analytic': analytic,
            'compliance_ref': 'cas9',
            'name': '导服成本 %s' % self.name,
        }, {
            'account_id': payable_acc.id,
            'partner_id': partner_id,
            'credit': net_pay,
            'analytic': analytic,
            'compliance_ref': 'cas9',
            'name': '应付导游分成 %s' % self.name,
        }, {
            'account_id': tax_acc.id,
            'credit': tax,
            'analytic': analytic,
            'compliance_ref': 'iit_labor',
            'name': '代扣个人所得税 %s' % self.name,
        }]

        move = self._tour_make_move(
            journal, fields.Date.context_today(self), self.name, lines,
            compliance_ref='cas9', narration=narration)
        move.action_post()
        return move.id

    def action_receive(self):
        for rec in self:
            if rec.state != 'confirmed':
                continue
            rec.state = 'received'

    def action_pay(self):
        """发放导游分成（税后实发）→ 生成付款凭证，幂等（pay_move_id 判断）。

        借 2241.02 其他应付款—导游分成 = guide_net_pay（只付实发净额，个税已计提）
            贷 1002 银行存款 = guide_net_pay
        [BS-10 §7.4.3 / TDS §5.5]
        """
        for rec in self:
            if rec.pay_move_id:
                continue  # 已发放，幂等
            if rec.state not in ('confirmed', 'received'):
                raise ValidationError('仅「已确认/已收款」佣金可发放')
            rec.pay_move_id = rec._generate_payment_move()
            rec.write({
                'state': 'paid',
                'pay_uid': self.env.user.id,
                'pay_date': fields.Datetime.now(),
            })

    def _get_payment_journal(self):
        self.ensure_one()
        if self.pay_journal_id:
            return self.pay_journal_id
        return self._tour_get_journal('bank')

    def _generate_payment_move(self):
        """生成导游分成发放付款凭证 [BS-10 §7.4.3]。"""
        self.ensure_one()
        net_pay = self.guide_net_pay or 0.0
        if net_pay <= 0:
            raise ValidationError('导游实发金额为 0，无法生成发放凭证')

        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_GUIDE)
        bank_acc = self._tour_get_account(self.ACCOUNT_BANK)
        journal = self._get_payment_journal()
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self.guide_id.partner_id.id if self.guide_id and self.guide_id.partner_id else None
        narration = '%s / %s / 发放导游分成' % (
            self.plan_code or '-', self.guide_id.name if self.guide_id else '未关联导游')

        lines = [{
            'account_id': payable_acc.id,
            'partner_id': partner_id,
            'debit': net_pay,
            'analytic': analytic,
            'compliance_ref': 'cas37',
            'name': '支付导游分成 %s' % self.name,
        }, {
            'account_id': bank_acc.id,
            'credit': net_pay,
            'analytic': analytic,
            'compliance_ref': 'pay_settle',
            'name': '支付导游分成 %s' % self.name,
        }]

        move = self._tour_make_move(
            journal, fields.Date.context_today(self), self.name, lines,
            compliance_ref='cas37', narration=narration)
        move.action_post()
        return move.id
