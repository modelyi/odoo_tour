# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

from odoo.addons.tour_base.models.constants import BIZ_MODE


class TourPlan(models.Model):
    _name = 'tour.plan'
    _description = '团队订单'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'plan_name'

    # === 标识 ===
    plan_code = fields.Char('团号', required=True, index=True, copy=False,
                            help='团号唯一，含 [变更-N] 版本后缀')
    plan_name = fields.Char('计划名称', required=True, index=True, tracking=True)
    line_id = fields.Many2one('tour.line', string='线路', required=True,
                              index=True, ondelete='restrict', tracking=True)
    contract_no = fields.Char('合同号', index=True)
    out_code = fields.Char('外部单号')

    # === 业务分类 ===
    biz_mode = fields.Selection(BIZ_MODE, string='业务模式', required=True, default='12', index=True,
       help='15 种业务模式（含别名码 2→DT、15→DSN、52→自由行），详见 BS-02 §5')
    plan_type = fields.Selection([
        ('1', '团队'),
        ('2', '散客/散拼'),
        ('5', '代订'),
        ('7', '变更团'),
    ], string='计划类型', required=True, default='2', index=True,
       help='1 团队 / 2 散客散拼 / 5 代订 / 7 变更团')
    plan_category = fields.Selection([
        ('regular', '常规旅游团'),
        ('fit', '散客计划'),
        ('independent', '自由行'),
        ('booking', '代订'),
        ('other', '其他'),
    ], string='计划分类', compute='_compute_plan_category', store=True, index=True,
       help='按业务模式自动归类：常规团(1,2,12,21) / 散客(13,14,15,31) / 自由行(51,52) / 代订(41) / 其他')
    from_type = fields.Selection([
        ('1', '内部'),
        ('5', '同行/组团'),
        ('4', '异常/疑似集团流转'),
    ], string='订单来源', default='1',
       help='源系统为数字编码：1 内部 / 5 同行 / 4 异常')
    reg_order_type = fields.Char('报名订单类型', help='源系统全 0，预留')
    plan_class = fields.Char('计划分类')

    # === 日期 ===
    begin_date = fields.Date('出发日期', required=True, index=True, tracking=True)
    end_date = fields.Date('返回日期', required=True, tracking=True)
    plan_begin_date = fields.Date('计划开始')
    plan_end_date = fields.Date('计划结束')
    main_begin_date = fields.Date('主团开始')
    main_end_date = fields.Date('主团结束')
    order_date = fields.Date('下单日期', default=fields.Date.context_today)

    # === 人数 ===
    guest_count = fields.Integer('客人数', required=True, default=0,
                                 help='有效客人数（不含婴儿）')
    adult_num = fields.Integer('成人数', default=0)
    child_num = fields.Integer('儿童数', default=0)
    old_man_num = fields.Integer('老人数', default=0)
    baby_num = fields.Integer('婴儿数', default=0)
    student_num = fields.Integer('学生数', default=0)
    guide_num = fields.Integer('随团导游数', default=0)
    valid_num = fields.Integer('有效人数', default=0)
    sum_adult_num = fields.Integer('成人数合计', default=0)
    sum_child_num = fields.Integer('儿童数合计', default=0)
    sum_oldman_num = fields.Integer('老人数合计', default=0)
    sum_baby_num = fields.Integer('婴儿数合计', default=0)
    sum_guide_num = fields.Integer('导游数合计', default=0)
    sum_student_num = fields.Integer('学生数合计', default=0)
    plan_num = fields.Integer('团队人数', default=0)

    # === 客户/联系人 ===
    supplier_id = fields.Many2one('res.partner', string='客户档案', index=True,
                                  tracking=True)
    supplier_name = fields.Char('客户名称')
    supplier_user = fields.Char('联系人')
    supplier_user_mobile = fields.Char('手机', help='🟡 敏感字段：界面脱敏')
    supplier_user_tel = fields.Char('座机')
    supplier_user_weixin = fields.Char('微信', help='🟡 敏感字段：界面脱敏')
    supplier_user_address = fields.Char('地址', help='🟡 敏感字段：界面脱敏')
    supplier_user_fax = fields.Char('传真')
    guest_contact = fields.Char('客人联系人')
    guest_occupation = fields.Char('客人职业', help='🟡 敏感字段：按权限脱敏展示')
    nation = fields.Char('民族')
    province = fields.Char('省份')
    city_name = fields.Char('城市')

    # === 接送/出团执行 ===
    receive_place = fields.Char('接站地点')
    receive_traffic = fields.Char('接站交通')
    receive_tag = fields.Char('接站标识')
    left_place = fields.Char('送站地点')
    left_traffic = fields.Char('送站交通')
    actual_shuttle_time = fields.Char('实际接送时间')
    out_state = fields.Char('出团状态')
    in_state = fields.Char('回团状态')
    is_received_guest = fields.Boolean('已接客')
    is_d_safe = fields.Boolean('已投保')
    is_send_hotel_dpt = fields.Boolean('已送酒店')
    gather_chk = fields.Boolean('集合确认')

    # === 房型 ===
    hotel_star = fields.Char('酒店星级')
    hotel_day_num = fields.Integer('入住天数', default=0)
    hotel_room_single = fields.Integer('单间数', default=0)
    hotel_room_standard = fields.Integer('标准间数', default=0)
    hotel_room_triangle = fields.Integer('三人间数', default=0)
    hotel_room_accompany = fields.Integer('陪同房数', default=0)
    hotel_room_additional = fields.Integer('加床房数', default=0)

    # === 金额（语义见 BS-02 §6） ===
    in_com_quo_sum = fields.Float('收入报价', digits=(16, 2),
                                  help='收入报价主字段')
    out_price_quo_sum = fields.Float('对外报价', digits=(16, 2),
                                     help='仅组团 BizMode=14 使用')
    pre_price_quo_sum = fields.Float('预报价', digits=(16, 2))
    sum_pay_normal = fields.Float('已收款', digits=(16, 2),
                                  help='已收款主字段')
    sum_pay = fields.Float('已收款合计', digits=(16, 2),
                           help='= 已收款 + 代收已付')
    sum_un_pay = fields.Float('未收款', digits=(16, 2),
                              help='应收账款余额（账龄分析依据）')
    sum_money_return = fields.Float('应退团款', digits=(16, 2))
    sum_pay_return = fields.Float('已退团款', digits=(16, 2))
    sum_money_delegate = fields.Float('代收金额', digits=(16, 2))
    sum_pay_delegate = fields.Float('代收已付', digits=(16, 2))
    in_sum = fields.Float('收入合计', digits=(16, 2))
    out_sum = fields.Float('成本合计', digits=(16, 2))
    profit = fields.Float('利润', digits=(16, 2))
    in_sum_no_shop = fields.Float('收入(不含购物)', digits=(16, 2))
    out_sum_no_shop = fields.Float('成本(不含购物)', digits=(16, 2))
    profit_no_shop = fields.Float('利润(不含购物)', digits=(16, 2))
    invoice_money = fields.Float('已开票金额', digits=(16, 2), help='实测未使用，预留')
    un_invoice_money = fields.Float('未开票金额', digits=(16, 2))
    sys_service_fee = fields.Float('系统服务费', digits=(16, 2), help='预留')
    currency = fields.Char('币种', default='人民币')
    exchange_rate = fields.Float('汇率', digits=(16, 6), default=1.0)

    # === 归属 ===
    sales_name = fields.Char('销售归属', index=True)
    channel_id = fields.Char('渠道 ID')
    channel_name = fields.Char('渠道名称')
    verify_user = fields.Char('核销人')
    verify_brief = fields.Text('核销说明')
    verify_user_cmp = fields.Char('核销人所属公司')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')
    user_id = fields.Many2one('res.users', string='操作员',
                              default=lambda self: self.env.user)
    in_user_id = fields.Many2one('res.users', string='录入人')
    update_user = fields.Char('最后更新人')

    # === 状态/审核 ===
    state = fields.Selection([
        ('draft', '草稿'),
        ('pending', '待确认'),
        ('confirmed', '已确认'),
        ('operating', '计调中'),
        ('in_progress', '出行中'),
        ('completed', '已完成'),
        ('archived', '已归档'),
        ('cancelled', '已取消'),
        ('refunded', '已退款'),
        ('void', '作废'),
    ], string='状态', default='draft', required=True, tracking=True, index=True)
    audit_chk = fields.Boolean('审核状态')
    audit_chk0 = fields.Boolean('初审状态')
    verify_chk = fields.Boolean('核销状态')
    verify_date = fields.Datetime('核销时间')
    op_state_chk = fields.Boolean('操作状态')
    zts_confirm_chk = fields.Boolean('组团社确认')
    reg_verification_chk = fields.Boolean('报名核销')
    is_contract = fields.Boolean('已签合同')

    # === 审核管理 ===
    operation_audit_state = fields.Selection([
        ('none', '未审核'),
        ('pending', '待审核'),
        ('approved', '已通过'),
        ('rejected', '已驳回'),
    ], string='计调审核状态', default='none', tracking=True, index=True)
    operation_audit_uid = fields.Many2one('res.users', string='计调审核人')
    operation_audit_date = fields.Datetime('计调审核时间')
    operation_audit_remark = fields.Text('计调审核备注')

    finance_audit_state = fields.Selection([
        ('none', '未审核'),
        ('pending', '待审核'),
        ('approved', '已通过'),
        ('rejected', '已驳回'),
    ], string='财务审核状态', default='none', tracking=True, index=True)
    finance_audit_uid = fields.Many2one('res.users', string='财务审核人')
    finance_audit_date = fields.Datetime('财务审核时间')
    finance_audit_remark = fields.Text('财务审核备注')

    # === 并团/溯源（核心：散客并团靠 first_plan_id） ===
    first_plan_id = fields.Many2one('tour.plan', string='首发计划', index=True,
                                    ondelete='restrict',
                                    help='首发计划（并团/变更溯源核心，99.6% 填充）')
    main_reg_id = fields.Many2one('tour.plan.reg', string='主报名单',
                                  help='主报名单（仅自由行 51/52 使用，其余恒空）')
    main_reg_code = fields.Char('主报名单号')

    # === 销售溯源（CRM 赢单转团回链，历史团可空，不 backfill） ===
    lead_id = fields.Many2one('crm.lead', string='销售线索', index=True,
                              copy=False, ondelete='set null',
                              help='CRM 赢单转团来源线索（历史团为空，不 backfill）')

    # === 导游安排（结构化拆分，禁止内嵌 PII） ===
    guide_contact = fields.Char('导游联系摘要')
    guide_ids = fields.Many2many('tour.guide', 'tour_plan_guide_rel',
                                 'plan_id', 'guide_id', string='导游安排',
                                 help='导游安排明细（结构化，禁止 JSON 内嵌 PII）')

    # === 备注 ===
    remark = fields.Text('备注')
    plan_remark = fields.Text('团队备注')
    plan_other_remark = fields.Text('其他备注')
    special_explain = fields.Text('特别说明')

    # === Smart Button 计数（报名）[界面改造样板] ===
    # One2many 反向关系：报名按 plan_id 挂到团，计数走 len(reg_ids)
    reg_ids = fields.One2many('tour.plan.reg', 'plan_id', string='报名明细')
    reg_count = fields.Integer('报名数', compute='_compute_reg_count')

    @api.depends('biz_mode')
    def _compute_plan_category(self):
        for rec in self:
            mode = rec.biz_mode
            if mode in ('1', '2', '12', '21'):
                rec.plan_category = 'regular'
            elif mode in ('13', '14', '15', '31'):
                rec.plan_category = 'fit'
            elif mode in ('51', '52'):
                rec.plan_category = 'independent'
            elif mode == '41':
                rec.plan_category = 'booking'
            else:
                rec.plan_category = 'other'

    @api.depends('reg_ids')
    def _compute_reg_count(self):
        for rec in self:
            rec.reg_count = len(rec.reg_ids)

    def action_view_regs(self):
        """Smart button：跳转到该团的报名列表。"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '报名',
            'res_model': 'tour.plan.reg',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    _uniq_plan_code = models.Constraint(
        'unique(plan_code)',
        '团号已存在',
    )

    @api.constrains('begin_date', 'end_date')
    def _check_date(self):
        for rec in self:
            if rec.begin_date and rec.end_date and rec.end_date < rec.begin_date:
                raise ValidationError('返回日期不能早于出发日期')

    @api.constrains('plan_begin_date', 'plan_end_date')
    def _check_plan_date(self):
        for rec in self:
            if (rec.plan_begin_date and rec.plan_end_date
                    and rec.plan_end_date < rec.plan_begin_date):
                raise ValidationError('计划结束日期不能早于计划开始日期')

    # === 状态机动作（目标状态机 BS-02 §3.5） ===
    def action_confirm(self):
        """草稿 → 待确认 → 已确认"""
        for rec in self:
            if rec.state == 'draft':
                rec.state = 'pending'
            elif rec.state == 'pending':
                rec.state = 'confirmed'

    def action_operate(self):
        """已确认 → 计调中"""
        for rec in self:
            if rec.state != 'confirmed':
                raise ValidationError('仅「已确认」订单可进入计调')
            rec.state = 'operating'

    def action_start(self):
        """计调中 → 出行中"""
        for rec in self:
            if rec.state not in ('confirmed', 'operating'):
                raise ValidationError('当前状态不允许出团')
            rec.state = 'in_progress'

    def action_complete(self):
        """出行中 → 已完成"""
        for rec in self:
            if rec.state != 'in_progress':
                raise ValidationError('仅「出行中」订单可完成')
            rec.state = 'completed'

    def action_archive(self):
        """已完成 → 已归档"""
        for rec in self:
            if rec.state != 'completed':
                raise ValidationError('仅「已完成」订单可归档')
            rec.state = 'archived'

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_refund(self):
        self.write({'state': 'refunded'})

    def action_void(self):
        self.write({'state': 'void'})

    def action_set_draft(self):
        self.write({'state': 'draft'})

    # === 审核管理 ===
    def action_submit_operation_audit(self):
        """提交计调审核"""
        for rec in self:
            if rec.state not in ('operating', 'in_progress', 'completed'):
                raise ValidationError('仅计调中/出行中/已完成的订单可提交计调审核')
            rec.operation_audit_state = 'pending'

    def action_approve_operation_audit(self):
        """通过计调审核"""
        for rec in self:
            if rec.operation_audit_state != 'pending':
                raise ValidationError('仅待审核的订单可通过')
            rec.write({
                'operation_audit_state': 'approved',
                'operation_audit_uid': self.env.user.id,
                'operation_audit_date': fields.Datetime.now(),
            })

    def action_reject_operation_audit(self):
        """驳回计调审核"""
        for rec in self:
            if rec.operation_audit_state != 'pending':
                raise ValidationError('仅待审核的订单可驳回')
            rec.write({
                'operation_audit_state': 'rejected',
                'operation_audit_uid': self.env.user.id,
                'operation_audit_date': fields.Datetime.now(),
            })

    def action_submit_finance_audit(self):
        """提交财务审核"""
        for rec in self:
            if rec.operation_audit_state != 'approved':
                raise ValidationError('需先通过计调审核')
            if rec.state not in ('in_progress', 'completed'):
                raise ValidationError('仅出行中/已完成的订单可提交财务审核')
            rec.finance_audit_state = 'pending'

    def action_approve_finance_audit(self):
        """通过财务审核"""
        for rec in self:
            if rec.finance_audit_state != 'pending':
                raise ValidationError('仅待审核的订单可通过')
            rec.write({
                'finance_audit_state': 'approved',
                'finance_audit_uid': self.env.user.id,
                'finance_audit_date': fields.Datetime.now(),
            })

    def action_reject_finance_audit(self):
        """驳回财务审核"""
        for rec in self:
            if rec.finance_audit_state != 'pending':
                raise ValidationError('仅待审核的订单可驳回')
            rec.write({
                'finance_audit_state': 'rejected',
                'finance_audit_uid': self.env.user.id,
                'finance_audit_date': fields.Datetime.now(),
            })
