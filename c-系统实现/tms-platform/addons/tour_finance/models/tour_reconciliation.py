# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourReconciliation(models.Model):
    _name = 'tour.reconciliation'
    _description = '对账'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('对账单号', required=True, copy=False, default='新建')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code('tour.reconciliation') or '新建'
        return super().create(vals_list)

    verify_type = fields.Selection([
        ('group_tour', '团款对账'),
        ('ditch', '地接对账'),
        ('vehicle', '车费对账'),
        ('ticket', '票务对账'),
        ('insurance', '保险对账'),
        ('meal', '餐费对账'),
        ('hotel', '房费对账'),
        ('scenic', '门票对账'),
        ('visa', '签证对账'),
        ('self_fee', '自费对账'),
        ('shop', '购物对账'),
        ('refund', '团款退款对账'),
        ('delegate', '代收对账'),
    ], string='对账类型', required=True, index=True,
       help='11 类往来对账 + 团款退款/代收两项（BS-07）')

    supplier_id = fields.Many2one('res.partner', string='对方单位', index=True)
    supplier_name = fields.Char('对方单位名称')
    period_begin = fields.Date('对账期间开始')
    period_end = fields.Date('对账期间结束')

    total_amount = fields.Float('应收/应付总额', digits=(16, 2))
    settled_amount = fields.Float('已收/已付总额', digits=(16, 2))
    unsettled_amount = fields.Float('未收/未付总额', digits=(16, 2),
                                    compute='_compute_unsettled', store=True)
    invoice_collected = fields.Float('已收集发票金额', digits=(16, 2),
                                     help='应付类对账的合规发票归集 [财税2016-36号]')
    invoice_gap = fields.Float('发票缺口', digits=(16, 2), compute='_compute_unsettled',
                               store=True, help='= 已付 - 已收集发票')
    aging_days = fields.Integer('最大账龄天数', help='应收账款账龄分析 [CAS 8-减值]')

    state = fields.Selection([
        ('pending', '待对账'),
        ('verified', '已对账'),
        ('settled', '已结清'),
    ], string='状态', default='pending', required=True, index=True)

    verify_user_id = fields.Many2one('res.users', string='对账人')
    verify_date = fields.Date('对账日期')
    confirm_user_id = fields.Many2one('res.users', string='确认人')
    confirm_date = fields.Date('确认日期')
    remark = fields.Text('备注')

    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    line_ids = fields.One2many('tour.reconciliation.line', 'reconciliation_id',
                               string='对账明细行')

    @api.depends('total_amount', 'settled_amount', 'invoice_collected')
    def _compute_unsettled(self):
        for rec in self:
            rec.unsettled_amount = (rec.total_amount or 0.0) - (rec.settled_amount or 0.0)
            rec.invoice_gap = (rec.settled_amount or 0.0) - (rec.invoice_collected or 0.0)

    @api.constrains('verify_user_id', 'confirm_user_id')
    def _check_separation(self):
        """对账人 ≠ 确认人（内控-职务分离）"""
        for rec in self:
            if rec.verify_user_id and rec.confirm_user_id \
                    and rec.verify_user_id == rec.confirm_user_id:
                raise ValidationError('对账人与确认人不能是同一人（不相容职务分离）')

    def action_verify(self):
        for rec in self:
            if rec.state != 'pending':
                raise ValidationError('仅「待对账」可核对')
            if not rec.verify_user_id:
                rec.verify_user_id = self.env.user
            rec.verify_date = fields.Date.context_today(self)
            rec.state = 'verified'

    def action_settle(self):
        for rec in self:
            if rec.state != 'verified':
                raise ValidationError('仅「已对账」可结清')
            if not rec.confirm_user_id:
                rec.confirm_user_id = self.env.user
            rec.confirm_date = fields.Date.context_today(self)
            rec.state = 'settled'


class TourReconciliationLine(models.Model):
    _name = 'tour.reconciliation.line'
    _description = '对账明细行'
    _order = 'id'

    reconciliation_id = fields.Many2one('tour.reconciliation', string='对账单',
                                        required=True, ondelete='cascade', index=True)
    plan_id = fields.Many2one('tour.plan', string='团队订单', index=True)
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    begin_date = fields.Date('出团日期', related='plan_id.begin_date', store=True)
    guest_count = fields.Integer('客人数', related='plan_id.guest_count', store=True)

    amount = fields.Float('应收/应付金额', digits=(16, 2))
    settled_amount = fields.Float('已收/已付金额', digits=(16, 2))
    unsettled_amount = fields.Float('未收/未付金额', digits=(16, 2),
                                    compute='_compute_unsettled', store=True)
    invoice_amount = fields.Float('已取得发票金额', digits=(16, 2))

    verify_state = fields.Selection([
        ('unverified', '未核对'),
        ('verified', '已核对'),
        ('diff', '有差异'),
    ], string='核对状态', default='unverified', required=True)
    diff_reason = fields.Text('差异原因')
    remark = fields.Text('备注')

    @api.depends('amount', 'settled_amount')
    def _compute_unsettled(self):
        for rec in self:
            rec.unsettled_amount = (rec.amount or 0.0) - (rec.settled_amount or 0.0)

    @api.constrains('verify_state', 'diff_reason')
    def _check_diff_reason(self):
        for rec in self:
            if rec.verify_state == 'diff' and not rec.diff_reason:
                raise ValidationError('核对状态为「有差异」时必须填写差异原因')
