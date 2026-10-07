# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaStaffAgreement(models.Model):
    """司陪导协议（BS-08 §4.6）：导游/司机/陪同的分成比例 + 人均线奖金规则 +
    税务类型（劳务报酬/工资薪金，[CAS 9 / 个税法] 决定个税计算方式）。"""
    _name = 'ta.staff.agreement'
    _description = '司陪导协议'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'id desc'

    name = fields.Char(string='协议编号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.staff.agreement') or '/')
    staff_type = fields.Selection([
        ('guide', '导游'),
        ('driver', '司机'),
        ('escort', '陪同'),
    ], string='人员类型', required=True, default='guide', tracking=True)
    staff_id = fields.Many2one('res.partner', string='人员', required=True, tracking=True)
    staff_name = fields.Char(related='staff_id.name', string='人员姓名')
    tax_type = fields.Selection([
        ('labor', '劳务报酬'),
        ('salary', '工资薪金'),
    ], string='税务类型', required=True, default='labor', tracking=True,
        help='劳务报酬：按 20%-40% 累进预扣；工资薪金：并入月度综合所得计税。')
    id_number = fields.Char(string='身份证号（脱敏）',
                            help='[个税法-代扣代缴] 仅存脱敏形式（如后四位），禁止存完整证件号。')
    share_rate = fields.Float(string='分成比例(%)', required=True, digits=(5, 2), tracking=True,
                              help='导游/司陪占佣金总额的分成比例；旅行社留存 = 100% − 各分成。')
    premium_rule_ids = fields.One2many('ta.staff.agreement.premium', 'agreement_id',
                                       string='奖金规则')
    state = fields.Selection([
        ('draft', '草稿'),
        ('active', '生效'),
        ('inactive', '已失效'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    note = fields.Char()

    _share_ratio = models.Constraint(
        'check(share_rate >= 0 and share_rate <= 100)', '分成比例必须在 0-100 之间。')

    def action_active(self):
        for a in self:
            if a.state != 'draft':
                raise UserError("只有草稿协议可以生效。")
            a.state = 'active'

    def action_inactive(self):
        for a in self:
            if a.state != 'active':
                raise UserError("只有生效协议可以置为已失效。")
            a.state = 'inactive'

    def _get_premium(self, per_capita):
        """BS-08 §4.6：奖金规则按人均购物下限匹配，取命中的最高档奖金。"""
        self.ensure_one()
        premium = 0.0
        for rule in self.premium_rule_ids.sorted('min_per_capita'):
            if per_capita >= rule.min_per_capita:
                premium = rule.premium_amount
        return premium


class TaStaffAgreementPremium(models.Model):
    """司陪导协议奖金规则（BS-08 §4.6）：达到人均购物下限发放奖金，奖金合并计税。"""
    _name = 'ta.staff.agreement.premium'
    _description = '司陪导协议奖金规则'
    _inherit = ['ta.mixin']
    _order = 'min_per_capita, id'

    agreement_id = fields.Many2one('ta.staff.agreement', ondelete='cascade', required=True)
    min_per_capita = fields.Float(string='人均购物下限', required=True, digits=(15, 2))
    premium_amount = fields.Float(string='奖金金额', required=True, digits=(15, 2),
                                  help='[个税法-劳务报酬] 奖金合并到当次分成中计算预扣个税。')

    _premium_positive = models.Constraint(
        'check(premium_amount >= 0)', '奖金金额不能为负。')
