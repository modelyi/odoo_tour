# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourLine(models.Model):
    _name = 'tour.line'
    _description = '线路产品（委托 product.template）'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # 委托继承：线路 = 一种 service 产品。表名与 id 不变，下游 FK（tour.plan.line_id 等）不断。
    # name / default_code / categ_id / list_price / active / is_published 等“产品主档”字段
    # 由 product.template 承接并自动代理，不在 tour.line 上重复定义。
    _inherits = {'product.template': 'product_tmpl_id'}
    _order = 'sequence, name'

    # === 委托主键（1:1 → product.template） ===
    product_tmpl_id = fields.Many2one(
        'product.template', string='产品模板', required=True,
        index=True, ondelete='cascade')

    # === 旅行社专属字段（保留在 tour.line，电商不直接消费） ===
    help_code = fields.Char('助记码', index=True)
    short_name = fields.Char('简称')
    sequence = fields.Integer('排序', default=10)

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

    # === 价格体系（成人价已委托 product.template.list_price） ===
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
    detail_count = fields.Integer('行程明细数', compute='_compute_detail_count')

    def _compute_departure_count(self):
        if not self.ids:
            return
        # 20 的 read_group 换签名（domain, groupby, aggregates）且返回元组列表，
        # 19 的 (domain, fields, groupby)+dict 写法会静默算错 → 统一走 _read_group。
        counts = self.env['tour.departure']._read_group(
            [('line_id', 'in', self.ids)], ['line_id'], ['__count'])
        mapped = {line.id: n for line, n in counts if line}
        for rec in self:
            rec.departure_count = mapped.get(rec.id, 0)

    def _compute_detail_count(self):
        if not self.ids:
            return
        counts = self.env['tour.line.detail']._read_group(
            [('line_id', 'in', self.ids)], ['line_id'], ['__count'])
        mapped = {line.id: n for line, n in counts if line}
        for rec in self:
            rec.detail_count = mapped.get(rec.id, 0)

    # === 动作 ===
    def action_view_departures(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '发团计划',
            'res_model': 'tour.departure',
            'view_mode': 'kanban,list,form',
            'domain': [('line_id', '=', self.id)],
            'context': {'default_line_id': self.id},
        }

    def action_view_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '行程明细',
            'res_model': 'tour.line.detail',
            'view_mode': 'list,form',
            'domain': [('line_id', '=', self.id)],
            'context': {'default_line_id': self.id},
        }

    def action_submit(self):
        self.write({'audit_state': 'submitted'})

    def action_approve(self):
        self.write({'audit_state': 'approved'})

    def action_reject(self):
        self.write({'audit_state': 'rejected'})

    def action_draft(self):
        self.write({'audit_state': 'draft'})
