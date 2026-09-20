# -*- coding: utf-8 -*-
"""团款应收催收台账（BS-12 §8.6 / §5.3）。

决策（BS-12 §5.3 双轨制）：
- account_followup 原生负责「催款等级 + 自动催款函」（客户维度）；
- tour.dunning 自建负责「按团催收台账 + 动作留痕 + 责任到人」。

催收动作留痕（tour.dunning.action）不可篡改 [内控-审计轨迹]：
operator_id / action_date 自动默认，不提供删除入口。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TourDunning(models.Model):
    _name = 'tour.dunning'
    _description = '团款应收催收台账'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    plan_id = fields.Many2one(
        'tour.plan', string='团', required=True, index=True,
        ondelete='restrict', help='催收对象团队（一团一核算）')
    plan_code = fields.Char(
        '团号', related='plan_id.plan_code', store=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='客户', related='plan_id.supplier_id', store=True,
        index=True)
    line_id = fields.Many2one(
        'tour.line', string='线路', related='plan_id.line_id', store=True,
        index=True)

    salesman_id = fields.Many2one(
        'res.users', string='责任销售员',
        default=lambda self: self.env.user,
        help='催收责任到人 [内控-对账机制]')

    overdue_amount = fields.Float(
        '逾期金额', digits=(16, 2), default=0.0,
        help='催收目标金额（通常 = 团款应收正数部分）')

    aging_bucket = fields.Selection([
        ('0_30', '0-30天'),
        ('31_90', '31-90天'),
        ('91_180', '91-180天'),
        ('181_365', '181-365天'),
        ('over_365', '>365天'),
    ], string='账龄区间', help='沿用 BS-05 AC-19 坏账计提区间')

    state = fields.Selection([
        ('pending', '待催收'),
        ('dunning', '催收中'),
        ('collected', '已回款'),
        ('written_off', '坏账核销'),
    ], string='催收状态', default='pending', required=True, index=True,
       tracking=True)

    dunning_action_ids = fields.One2many(
        'tour.dunning.action', 'dunning_id', string='催收动作')

    company_id = fields.Many2one(
        'res.company', string='所属公司', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    def action_view_plan_account(self):
        self.ensure_one()
        account = self.env['tour.plan.account'].search(
            [('plan_id', '=', self.plan_id.id)], limit=1)
        if not account:
            return {'type': 'ir.actions.act_window', 'name': '单团核算', 'res_model': 'tour.plan.account', 'view_mode': 'list,form'}
        return {
            'type': 'ir.actions.act_window',
            'name': '单团核算',
            'res_model': 'tour.plan.account',
            'view_mode': 'form',
            'res_id': account.id,
        }

    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        """选团后按未收款正数部分预填逾期金额与账龄区间。"""
        if self.plan_id:
            unpay = self.plan_id.sum_un_pay or 0.0
            self.overdue_amount = unpay if unpay > 0 else 0.0

    @api.constrains('plan_id')
    def _check_plan_unique_active(self):
        """同一团最多一条未完结（待催收/催收中）的催收记录，避免重复催收。"""
        for rec in self:
            if rec.state not in ('pending', 'dunning'):
                continue
            dup = self.search([
                ('plan_id', '=', rec.plan_id.id),
                ('state', 'in', ('pending', 'dunning')),
                ('id', '!=', rec.id),
            ])
            if dup:
                raise ValidationError(
                    '团队「%s」已存在未完结的催收记录，请先结清或核销后再建'
                    % (rec.plan_code or ''))

    def action_start_dunning(self):
        """待催收 → 催收中"""
        for rec in self:
            if rec.state != 'pending':
                raise ValidationError('仅「待催收」记录可开始催收')
            rec.state = 'dunning'

    def action_collected(self):
        """催收中 → 已回款（核销后手动结案）"""
        for rec in self:
            if rec.state != 'dunning':
                raise ValidationError('仅「催收中」记录可标记已回款')
            rec.state = 'collected'

    def action_write_off(self):
        """催收中 → 坏账核销（连续催收仍不还 → 提级 → 坏账计提 [CAS 22]）"""
        for rec in self:
            if rec.state != 'dunning':
                raise ValidationError('仅「催收中」记录可坏账核销')
            rec.state = 'written_off'

    def action_reset(self):
        """回退到待催收（误操作纠正）"""
        for rec in self:
            rec.state = 'pending'


class TourDunningAction(models.Model):
    _name = 'tour.dunning.action'
    _description = '催收动作留痕'
    _order = 'action_date desc, id desc'

    dunning_id = fields.Many2one(
        'tour.dunning', string='催收记录', required=True,
        ondelete='cascade', index=True)

    action_type = fields.Selection([
        ('call', '电话'),
        ('email', '邮件'),
        ('visit', '上门'),
        ('legal', '法务'),
    ], string='催收方式', required=True)

    operator_id = fields.Many2one(
        'res.users', string='催收人', default=lambda self: self.env.user)
    action_date = fields.Datetime(
        '催收时间', default=fields.Datetime.now)
    note = fields.Text('催收记录')
