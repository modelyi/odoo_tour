# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

from odoo.addons.tour_base.models.constants import BIZ_MODE


class TourPlanReg(models.Model):
    _name = 'tour.plan.reg'
    _description = '订单报名'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'reg_code'

    # === 标识与并团（核心：散客并团靠 first_plan_id） ===
    reg_code = fields.Char('报名单号', required=True, index=True, copy=False,
                           help='报名单号，并团后各报名单保留独立 reg_code')
    plan_id = fields.Many2one('tour.plan', string='所属团队订单', index=True,
                              ondelete='restrict', tracking=True)
    first_plan_id = fields.Many2one('tour.plan', string='首次挂接发团计划', index=True,
                                    ondelete='restrict',
                                    help='散客并团核心指针：并入哪个计划就指向哪个计划')
    main_reg_id = fields.Many2one('tour.plan.reg', string='主报名单',
                                  help='仅自由行 51/52 使用，其余恒空')
    main_reg_code = fields.Char('主报名单号')
    plan_id_main_reg = fields.Many2one('tour.plan', string='主报名所属团队')
    contract_no = fields.Char('合同号')
    out_code = fields.Char('外部单号')

    # === 业务分类与日期 ===
    biz_mode = fields.Selection(BIZ_MODE, string='业务模式', required=True, default='12', index=True)
    plan_type = fields.Selection([
        ('1', '团队'),
        ('2', '散客/散拼'),
        ('5', '代订'),
        ('7', '变更团'),
    ], string='计划类型', required=True, default='2', index=True)
    from_type = fields.Selection([
        ('1', '内部'),
        ('5', '同行/组团'),
        ('4', '异常/疑似集团流转'),
    ], string='订单来源', default='1')
    plan_class = fields.Char('计划分类')
    begin_date = fields.Date('出发日期', required=True, index=True)
    end_date = fields.Date('返回日期', required=True)
    order_date = fields.Date('下单日期', default=fields.Date.context_today)
    hotel_day_num = fields.Integer('入住天数', default=0)

    # === 人数 ===
    guest_count = fields.Integer('客人数', required=True, default=0,
                                 help='有效客人数（不含婴儿）')
    adult_num = fields.Integer('成人数', default=0)
    child_num = fields.Integer('儿童数', default=0)
    old_man_num = fields.Integer('老人数', default=0)
    baby_num = fields.Integer('婴儿数', default=0)
    student_num = fields.Integer('学生数', default=0)
    guide_num = fields.Integer('导游数', default=0)

    # === 客户/联系人 ===
    supplier_id = fields.Many2one('res.partner', string='客户', index=True)
    supplier_name = fields.Char('客户名称')
    supplier_user = fields.Char('联系人')
    supplier_user_mobile = fields.Char('手机', help='🟡 敏感字段：界面脱敏')
    supplier_user_tel = fields.Char('座机')
    supplier_user_fax = fields.Char('传真')
    guest_occupation = fields.Char('客人职业', help='🟡 敏感字段：按权限脱敏展示')
    nation = fields.Char('民族')
    province = fields.Char('省份')
    city_name = fields.Char('城市')

    # === 接送 ===
    receive_place = fields.Char('接站地点')
    receive_traffic = fields.Char('接站交通')
    receive_tag = fields.Char('接站标识')
    left_place = fields.Char('送站地点')
    left_traffic = fields.Char('送站交通')
    actual_shuttle_time = fields.Char('实际接送时间')
    out_state = fields.Char('出团状态')
    in_state = fields.Char('回团状态')
    gather_chk = fields.Boolean('集合确认')

    # === 房型 ===
    hotel_star = fields.Char('酒店星级')
    hotel_room_single = fields.Integer('单间', default=0)
    hotel_room_standard = fields.Integer('标准间', default=0)
    hotel_room_triangle = fields.Integer('三人间', default=0)
    hotel_room_accompany = fields.Integer('陪同房', default=0)
    hotel_room_additional = fields.Integer('加床', default=0)

    # === 金额（语义见 BS-02 §6） ===
    in_com_quo_sum = fields.Float('收入报价', digits=(16, 2),
                                  help='报名单层主报价字段')
    out_price_quo_sum = fields.Float('对外报价', digits=(16, 2))
    pre_price_quo_sum = fields.Float('预报价', digits=(16, 2))
    pre_cost_quo_sum = fields.Float('预成本', digits=(16, 2), help='实测未使用')
    sum_pay_normal = fields.Float('已收款', digits=(16, 2))
    sum_un_pay = fields.Float('未收款', digits=(16, 2))
    sum_money_delegate = fields.Float('代收金额', digits=(16, 2))
    sum_pay_delegate = fields.Float('代收已付', digits=(16, 2))
    sum_money_return = fields.Float('应退', digits=(16, 2))
    sum_pay_return = fields.Float('已退', digits=(16, 2))

    # === 状态/归属/备注 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('cancelled', '已取消'),
    ], string='状态', default='draft', required=True, tracking=True, index=True)
    audit_chk = fields.Boolean('审核')
    audit_chk0 = fields.Boolean('初审')
    verify_chk = fields.Boolean('核销')
    verify_date = fields.Datetime('核销时间')
    reg_verification_chk = fields.Boolean('报名核销')
    sales_name = fields.Char('销售归属', index=True)
    in_user_id = fields.Many2one('res.users', string='录入人')
    op_user_id = fields.Many2one('res.users', string='操作员',
                                 default=lambda self: self.env.user)
    update_user = fields.Char('更新人')
    remark = fields.Text('备注')

    _uniq_reg_code = models.Constraint(
        'unique(reg_code)',
        '报名单号已存在',
    )

    @api.constrains('begin_date', 'end_date')
    def _check_date(self):
        for rec in self:
            if rec.begin_date and rec.end_date and rec.end_date < rec.begin_date:
                raise ValidationError('返回日期不能早于出发日期')

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError('仅草稿状态可确认')
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise ValidationError('仅已取消状态可重置草稿')
        self.write({'state': 'draft'})
