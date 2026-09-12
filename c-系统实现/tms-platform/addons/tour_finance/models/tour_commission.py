# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourCommission(models.Model):
    _name = 'tour.commission'
    _description = '佣金（含个税代扣）'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
    ], string='状态', default='draft', required=True, index=True)
    confirm_uid = fields.Many2one('res.users', string='确认人')
    confirm_date = fields.Datetime('确认时间')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

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

    def action_receive(self):
        for rec in self:
            if rec.state != 'confirmed':
                continue
            rec.state = 'received'
