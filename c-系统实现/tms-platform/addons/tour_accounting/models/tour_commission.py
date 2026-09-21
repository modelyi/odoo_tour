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
            if not vals.get('employee_id') and vals.get('guide_id'):
                guide = self.env['tour.guide'].browse(vals['guide_id'])
                if guide.employee_id:
                    vals['employee_id'] = guide.employee_id.id
        return super().create(vals_list)

    # === 佣金来源 ===
    plan_id = fields.Many2one('tour.plan', string='团队订单', required=True, index=True,
                              ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    shop_id = fields.Many2one('tour.supplier', string='购物店', index=True,
                              domain=[('sup_type', '=', 'shop')])
    shop_name = fields.Char('购物店名称')
    agreement_id = fields.Many2one('tour.shop.agreement', string='购物协议',
                                   help='返佣比例来源 [印花税法-合同]')
    commission_rate = fields.Float('返佣比例(%)', digits=(5, 2))
    shop_amount = fields.Float('购物金额', digits=(16, 2))
    commission_total = fields.Float('佣金总额(经营收入)', digits=(16, 2),
                                    help='购物店返佣，属经营收入，不可冲减成本 [增值税暂行条例]')

    # === 导游分成 ===
    # 财务人事线：佣金发放人维度挂 hr.employee；个税类型读员工用工类型
    employee_id = fields.Many2one('hr.employee', string='导游（员工）', index=True,
                                  ondelete='restrict',
                                  help='佣金发放/个税代扣统一挂员工维度；个税类型按用工类型判定')
    guide_id = fields.Many2one('tour.guide', string='导游', index=True)
    guide_share_rate = fields.Float('导游分成比例(%)', digits=(5, 2))
    guide_share_before_tax = fields.Float('导游税前分成', digits=(16, 2))
    premium = fields.Float('导游奖金(税前)', digits=(16, 2),
                           help='人均线奖金，合并计入当次个税 [个税法-劳务报酬]')

    # === 个税代扣 ===
    guide_tax_type = fields.Selection([
        ('labor', '劳务报酬'),
        ('salary', '工资薪金'),
    ], string='税务类型', compute='_compute_guide_tax_type', store=True,
       help='按员工用工类型自动判定：劳动合同→工资薪金；劳务协议/挂靠、临时→劳务报酬 [CAS 9 / 个税法]')
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
    revenue_move_id = fields.Many2one('account.move', string='收款凭证', copy=False,
                                      ondelete='restrict', index=True,
                                      help='收款时生成的收入确认凭证（借银行存款/贷佣金收入+应付导游分成）[BS-08]')
    revenue_move_state = fields.Selection(related='revenue_move_id.state', string='收款凭证状态')
    pay_move_id = fields.Many2one('account.move', string='发放凭证', copy=False,
                                  ondelete='restrict', index=True,
                                  help='发放时生成的付款凭证（借应付导游/贷资金）[Phase 2 深化]')
    pay_move_state = fields.Selection(related='pay_move_id.state', string='发放凭证状态')
    pay_journal_id = fields.Many2one('account.journal', string='付款日记账',
                                     help='发放导游分成落账日记账；留空按银行存款日记账（bank）路由')

    # === 界面可视化（smart button 计数） ===
    move_count = fields.Integer('计提凭证数', compute='_compute_move_count')
    revenue_move_count = fields.Integer('收款凭证数', compute='_compute_move_count')
    pay_move_count = fields.Integer('发放凭证数', compute='_compute_move_count')

    @api.depends('move_id', 'revenue_move_id', 'pay_move_id')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = 1 if rec.move_id else 0
            rec.revenue_move_count = 1 if rec.revenue_move_id else 0
            rec.pay_move_count = 1 if rec.pay_move_id else 0

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': '计提凭证',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }

    def action_view_revenue_move(self):
        self.ensure_one()
        if not self.revenue_move_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': '收款凭证',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.revenue_move_id.id,
            'target': 'current',
        }

    def action_view_pay_move(self):
        self.ensure_one()
        if not self.pay_move_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': '发放凭证',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.pay_move_id.id,
            'target': 'current',
        }

    @api.depends('employee_id.employment_type')
    def _compute_guide_tax_type(self):
        for rec in self:
            rec.guide_tax_type = (
                'salary' if rec.employee_id.employment_type == 'labor_contract'
                else 'labor')

    @api.onchange('guide_id')
    def _onchange_guide_id(self):
        if self.guide_id and self.guide_id.employee_id:
            self.employee_id = self.guide_id.employee_id

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and not self.guide_id:
            guide = self.env['tour.guide'].search(
                [('employee_id', '=', self.employee_id.id)], limit=1)
            if guide:
                self.guide_id = guide

    @api.depends('commission_total', 'guide_share_before_tax', 'premium', 'guide_tax_type')
    def _compute_tax(self):
        for rec in self:
            before_tax = (rec.guide_share_before_tax or 0.0) + (rec.premium or 0.0)
            if rec.guide_tax_type == 'labor':
                rec.guide_tax = self._calc_labor_tax(before_tax)
            else:
                # 工资薪金代扣（累计预扣法 3%-45% 累进）
                rec.guide_tax = rec._calc_salary_tax(before_tax)
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

    def _calc_salary_tax(self, current_income):
        """工资薪金个税 - 累计预扣法 [个税法 - 工资薪金]
        
        累计预扣预缴应纳税所得额 = 累计收入 - 累计免税收入 - 累计减除费用 - 
                                  累计专项扣除 - 累计专项附加扣除 - 累计依法确定的其他扣除
        
        本期应预扣预缴税额 = (累计预扣预缴应纳税所得额 × 预扣率 - 速算扣除数) - 
                           累计减免税额 - 累计已预扣预缴税额
        
        减除费用：5000 元/月 (60000 元/年)
        税率表 (综合所得适用):
        - 不超过 36000: 3%, 速算扣除数 0
        - 36000-144000: 10%, 速算扣除数 2520
        - 144000-300000: 20%, 速算扣除数 16920
        - 300000-420000: 25%, 速算扣除数 31920
        - 420000-660000: 30%, 速算扣除数 52920
        - 660000-960000: 35%, 速算扣除数 85920
        - 超过 960000: 45%, 速算扣除数 181920
        """
        if not self.employee_id:
            return 0.0
        
        current_income = current_income or 0.0
        if current_income <= 0:
            return 0.0
        
        # 获取当前期间 (从 plan_id 的 begin_date 或当前日期)
        if self.plan_id and self.plan_id.begin_date:
            current_date = self.plan_id.begin_date
        else:
            current_date = fields.Date.today()
        
        current_year = current_date.year
        current_month = current_date.month
        
        # 查询本年已确认/已发放的佣金 (同员工)
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('state', 'in', ['confirmed', 'received', 'paid']),
            ('guide_tax_type', '=', 'salary'),
        ]
        
        # 获取本年所有记录
        all_records = self.search(domain)
        
        # 计算累计收入 (不含当前记录)
        ytd_income = 0.0
        ytd_tax = 0.0
        for record in all_records:
            if record.plan_id and record.plan_id.begin_date:
                record_month = record.plan_id.begin_date.month
                record_year = record.plan_id.begin_date.year
                if record_year == current_year and record_month < current_month:
                    ytd_income += (record.guide_share_before_tax or 0.0) + (record.premium or 0.0)
                    ytd_tax += record.guide_tax or 0.0
            elif not record.plan_id:
                # 如果没有 plan_id，按 create_date 判断
                if record.create_date and record.create_date.year == current_year:
                    if record.create_date.month < current_month:
                        ytd_income += (record.guide_share_before_tax or 0.0) + (record.premium or 0.0)
                        ytd_tax += record.guide_tax or 0.0
        
        # 累计收入 (含当前)
        total_income = ytd_income + current_income
        
        # 累计减除费用 (5000/月)
        total_deduction = 5000 * current_month
        
        # 累计专项扣除 (社保 + 公积金) - 简化处理，假设每月 1000 元
        # TODO: 应从 hr.employee 或 hr.payroll 获取实际数据
        special_deduction = 1000 * current_month
        
        # 累计应纳税所得额
        taxable_income = total_income - total_deduction - special_deduction
        taxable_income = max(0, taxable_income)
        
        # 计算累计应纳税额 (累进税率)
        cumulative_tax = self._apply_progressive_tax(taxable_income)
        
        # 本期应预扣税额 = 累计税额 - 已预扣税额
        current_tax = cumulative_tax - ytd_tax
        current_tax = max(0, current_tax)
        
        return round(current_tax, 2)
    
    @staticmethod
    def _apply_progressive_tax(taxable_income):
        """应用累进税率表 (综合所得)"""
        if taxable_income <= 0:
            return 0.0
        
        if taxable_income <= 36000:
            return taxable_income * 0.03
        elif taxable_income <= 144000:
            return taxable_income * 0.10 - 2520
        elif taxable_income <= 300000:
            return taxable_income * 0.20 - 16920
        elif taxable_income <= 420000:
            return taxable_income * 0.25 - 31920
        elif taxable_income <= 660000:
            return taxable_income * 0.30 - 52920
        elif taxable_income <= 960000:
            return taxable_income * 0.35 - 85920
        else:
            return taxable_income * 0.45 - 181920

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
        partner_id = self._tour_partner_id()
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
        """购物店返佣到账 → 确认收入（旅行社留存）+ 确认应付导游分成 [BS-08]。

        借 1002 银行存款 = commission_total
            贷 6050 佣金收入 = company_retain
            贷 2241.02 其他应付款—导游分成 = guide_share_before_tax + premium
        """
        for rec in self:
            if rec.state != 'confirmed':
                continue
            if not rec.revenue_move_id:
                rec.revenue_move_id = rec._generate_revenue_move()
            rec.state = 'received'

    def _generate_revenue_move(self):
        """生成佣金收款收入确认凭证 [BS-08 §3]。"""
        self.ensure_one()
        total = self.commission_total or 0.0
        retain = self.company_retain or 0.0
        before_tax = (self.guide_share_before_tax or 0.0) + (self.premium or 0.0)
        if total <= 0:
            raise ValidationError('佣金总额为 0，无法生成收款凭证')

        bank_acc = self._tour_get_account(self.ACCOUNT_BANK)
        revenue_acc = self._tour_get_account(self.ACCOUNT_REVENUE_COMMISSION)
        payable_acc = self._tour_get_account(self.ACCOUNT_PAYABLE_GUIDE)
        journal = self._tour_get_journal('bank')
        analytic = self._plan_analytic_distribution(self.plan_id)
        partner_id = self._tour_partner_id()
        narration = '%s / %s / 佣金收款确认' % (
            self.plan_code or '-', self.shop_id.name if self.shop_id else '未关联购物店')

        lines = [{
            'account_id': bank_acc.id,
            'debit': total,
            'analytic': analytic,
            'compliance_ref': 'cas14',
            'name': '收到佣金 %s' % self.name,
        }, {
            'account_id': revenue_acc.id,
            'credit': retain,
            'analytic': analytic,
            'compliance_ref': 'cas14',
            'name': '佣金收入（旅行社留存）%s' % self.name,
        }, {
            'account_id': payable_acc.id,
            'partner_id': partner_id,
            'credit': before_tax,
            'analytic': analytic,
            'compliance_ref': 'cas9',
            'name': '应付导游分成 %s' % self.name,
        }]

        move = self._tour_make_move(
            journal, fields.Date.context_today(self), self.name, lines,
            compliance_ref='cas14', narration=narration)
        move.action_post()
        return move.id

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
        partner_id = self._tour_partner_id()
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
