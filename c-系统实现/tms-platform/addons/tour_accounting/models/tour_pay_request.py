# -*- coding: utf-8 -*-
"""请款单（采购到付款审批）——P2P 付款审批前置 [TDS §2.3 / BS-06 plan.pay.audit.flow]。

链路：tour.plan.out_sum（成本合计）→ vendor bill（account.move in_invoice）
      → 请款单（分级审批 state 机）→ account.payment（原生 register payment）
      → 核销应付（Odoo 原生 reconcile）。

成本侧无分项（源 CSV 只有 OutSum 合计），成本总额统一挂「主营业务成本 6401」，
应付统一挂「应付账款 2202」，后续有分项数据再按 cost_type→6401.0N 映射细分。
"""
from odoo import models, fields, api

COST_TYPE_SELECTION = [
    ('local_guide', '地接费'),
    ('hotel', '住宿费'),
    ('meal', '餐费'),
    ('vehicle', '交通费'),
    ('ticket', '门票费'),
    ('guide', '导服费'),
    ('insurance', '保险费'),
    ('visa', '签证费'),
    ('self_pay', '自费项目'),
    ('shopping', '购物成本'),
    ('other', '其他/合计'),
]


class TourPayRequest(models.Model):
    _name = 'tour.pay.request'
    _description = '请款单（采购付款审批）'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.accounting.mixin']
    _order = 'apply_date desc, id desc'

    # === 标识 ===
    name = fields.Char('请款单号', required=True, copy=False, default='新建',
                       help='自动流水，如 QK-000123')

    # === 业务关联 ===
    plan_id = fields.Many2one('tour.plan', string='团队', required=True,
                              index=True, ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    supplier_id = fields.Many2one('res.partner', string='供应商(付款对象)',
                                  index=True)
    bill_id = fields.Many2one('account.move', string='应付账单',
                              domain="[('move_type', '=', 'in_invoice')]",
                              ondelete='restrict', index=True,
                              help='对应 vendor bill（account.move in_invoice）')
    bill_state = fields.Selection(related='bill_id.state', string='账单状态')

    # === 请款金额与科目 ===
    amount = fields.Float('请款金额', digits=(16, 2), required=True,
                          help='= tour.plan.out_sum（成本合计，含税口径）')
    cost_type = fields.Selection(COST_TYPE_SELECTION, string='成本类型',
                                 default='other', required=True,
                                 help='源数据无分项成本，默认「其他/合计」统一挂 6401')
    cost_account_id = fields.Many2one('account.account', string='成本科目',
                                      domain="[('account_type', 'in', ('expense', 'expense_direct_cost'))]",
                                      help='留空默认「主营业务成本 6401」')

    # === 审批 ===
    state = fields.Selection([
        ('draft', '待审批'),
        ('approved', '已审批'),
        ('paid', '已付款'),
        ('rejected', '已驳回'),
    ], string='状态', default='draft', required=True, index=True, tracking=True)
    audit_level = fields.Selection([
        ('none', '免审'),
        ('l1', '一级审批'),
        ('l2', '二级审批'),
        ('l3', '三级双签'),
    ], string='审批级别', compute='_compute_audit_level', store=True,
       help='按金额阈值：免审≤1000 / 一级 1001-5万 / 二级 5万-20万 / 三级>20万 双签')
    applicant_id = fields.Many2one('res.users', string='申请人',
                                   default=lambda self: self.env.user)
    approver_id = fields.Many2one('res.users', string='审批人')
    approve_date = fields.Datetime('审批时间')
    apply_date = fields.Date('申请日期', default=fields.Date.context_today, required=True)
    reason = fields.Char('付款事由')

    # === 付款回链 ===
    payment_id = fields.Many2one('account.payment', string='付款单',
                                 ondelete='restrict', index=True)
    payment_state = fields.Selection(related='payment_id.state', string='付款状态')

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    # === 界面可视化（smart button 计数） ===
    bill_count = fields.Integer('账单数', compute='_compute_link_count')
    payment_count = fields.Integer('付款单数', compute='_compute_link_count')

    @api.depends('bill_id', 'payment_id')
    def _compute_link_count(self):
        for rec in self:
            rec.bill_count = 1 if rec.bill_id else 0
            rec.payment_count = 1 if rec.payment_id else 0

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': '应付账单',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.bill_id.id,
            'target': 'current',
        }

    def action_view_payment(self):
        self.ensure_one()
        if not self.payment_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': '付款单',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.payment_id.id,
            'target': 'current',
        }

    _uniq_pay_request_name = models.Constraint(
        'unique(name)', '请款单号已存在')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tour.pay.request') or '新建'
        return super().create(vals_list)

    @api.depends('amount', 'company_id.tour_pr_free_limit',
                 'company_id.tour_pr_approve_limit_l1',
                 'company_id.tour_pr_approve_limit_l2')
    def _compute_audit_level(self):
        for rec in self:
            rec.audit_level = rec._audit_level_for(rec.amount or 0.0)

    def _audit_level_for(self, amount):
        """按金额分级（阈值存 res.company，默认 1000 / 5万 / 20万）[BS-06 §4.2]"""
        co = self.company_id or self.env.company
        free = co.tour_pr_free_limit or 1000.0
        l1 = co.tour_pr_approve_limit_l1 or 50000.0
        l2 = co.tour_pr_approve_limit_l2 or 200000.0
        if amount <= free:
            return 'none'
        if amount <= l1:
            return 'l1'
        if amount <= l2:
            return 'l2'
        return 'l3'

    # === 状态机 ===
    def action_approve(self):
        """待审批 → 已审批（幂等：非待审批优雅跳过）[UAT P3]。"""
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'approve_date': fields.Datetime.now(),
            })

    def action_pay(self):
        """已审批 → 已付款（须已生成付款单 payment_id）。"""
        for rec in self:
            if rec.state != 'approved':
                continue
            if not rec.payment_id:
                continue
            rec.state = 'paid'

    def action_reject(self):
        """待审批 → 已驳回。"""
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.state = 'rejected'
