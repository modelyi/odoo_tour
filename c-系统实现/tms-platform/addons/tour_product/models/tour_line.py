# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourLine(models.Model):
    _name = 'tour.line'
    _description = '线路产品'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    # === 基本信息 ===
    name = fields.Char('线路名称', required=True, tracking=True, index=True)
    code = fields.Char('线路编号', index=True, copy=False)
    help_code = fields.Char('助记码', index=True)
    short_name = fields.Char('简称')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True, tracking=True)

    # === 分类 ===
    line_type_id = fields.Many2one('tour.line.type', string='线路分类', required=True, index=True, tracking=True)

    # === 行程信息 ===
    day_num = fields.Integer('天数', required=True, default=1)
    night_num = fields.Integer('夜数', default=0)
    send_place = fields.Char('出发地')
    end_place = fields.Char('目的地')
    from_province = fields.Char('出发省份')
    from_city = fields.Char('出发城市')
    to_province = fields.Char('目的省份')
    to_city = fields.Char('目的城市')
    send_traffic = fields.Char('去程交通')
    end_traffic = fields.Char('返程交通')

    # === 价格体系 ===
    adult_price = fields.Float('成人价', digits='Product Price')
    child_price = fields.Float('儿童价', digits='Product Price')
    old_man_price = fields.Float('老人价', digits='Product Price')
    student_price = fields.Float('学生价', digits='Product Price')
    baby_price = fields.Float('婴儿价', digits='Product Price')
    fee_include = fields.Text('费用包含')
    fee_exclude = fields.Text('费用不含')

    # === 内容 ===
    srv_text = fields.Html('行程安排')
    details_rich = fields.Html('行程详情')
    feature_rich = fields.Html('线路特色')
    shopping_info = fields.Text('购物信息')
    self_paid_item = fields.Text('自费项目')
    warm_hint = fields.Text('温馨提示')
    attentions = fields.Text('注意事项')

    # === 业务关联 ===
    dj_supplier_id = fields.Many2one('res.partner', string='地接社', domain=[('supplier_rank', '>', 0)])
    guide_share_rate = fields.Float('导游分成比例(%)', digits=(5, 2))
    guide_premium = fields.Float('导游奖金', digits='Product Price')

    # === 状态 ===
    is_special = fields.Boolean('特殊线路')
    is_abroad = fields.Boolean('境外线路')
    audit_state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '待审核'),
        ('approved', '已审核'),
        ('rejected', '已拒绝'),
    ], string='审核状态', default='draft', tracking=True)

    # === 关联 ===
    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='负责人', default=lambda self: self.env.user)
    department_name = fields.Char('部门')

    # === 统计 ===
    departure_count = fields.Integer('发团计划数', compute='_compute_departure_count')

    def _compute_departure_count(self):
        for rec in self:
            rec.departure_count = 0  # TODO: link departure plans

    # === 动作 ===
    def action_submit(self):
        self.write({'audit_state': 'submitted'})

    def action_approve(self):
        self.write({'audit_state': 'approved'})

    def action_reject(self):
        self.write({'audit_state': 'rejected'})

    def action_draft(self):
        self.write({'audit_state': 'draft'})
