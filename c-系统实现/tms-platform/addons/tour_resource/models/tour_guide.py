# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourGuide(models.Model):
    _name = 'tour.guide'
    _description = '导游档案'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, guide_code'

    # === 身份底座：res.partner（独立，不依赖 hr.employee）===
    partner_id = fields.Many2one('res.partner', string='关联联系人', index=True,
                                 ondelete='set null',
                                 help='导游的身份联系人；内部导游可关联员工 work_contact，外部导游可关联任意 partner')

    # === 劳动关系（可选：内部导游挂员工，外部导游不挂）===
    employee_id = fields.Many2one('hr.employee', string='员工档案', index=True,
                                  ondelete='set null',
                                  help='导游的劳动关系档案（用工类型/部门/在职）；借款/报销/佣金按员工维度挂账；1:1 导游↔员工')

    # === 基本信息 ===
    name = fields.Char('导游姓名', required=True, index=True, tracking=True)
    help_code = fields.Char('助记码', index=True, help='姓名拼音首字母自动生成，支持手工覆盖')
    guide_code = fields.Char('导游证号', required=True, index=True, copy=False,
                             help='全局唯一，保存时校验重复')
    sex = fields.Selection([
        ('male', '男'),
        ('female', '女'),
    ], string='性别')
    nation = fields.Char('民族')
    born_place = fields.Char('出生地')
    edu = fields.Char('学历')
    id_num = fields.Char('身份证号')
    tel = fields.Char('固定电话')
    mobile = fields.Char('手机号')
    zip_code = fields.Char('邮编')
    addr = fields.Char('通讯地址')
    photo = fields.Binary('照片')
    remark = fields.Text('备注')

    # === 导游资质 ===
    language_name = fields.Char('语言能力')
    licence = fields.Char('执照（导游资格证号）')
    licence_type = fields.Char('执照类型')
    guide_type = fields.Char('导游类型')
    guide_leader = fields.Boolean('是否领队')
    is_tour_guide = fields.Boolean('是否导游')
    is_driver_guide = fields.Boolean('是否司机兼导游')
    guide_lead_type = fields.Char('带团类型')
    guide_account = fields.Char('登录账号', help='登录密码走 Odoo 统一用户体系（关联 res.users）')
    job_no = fields.Char('工号')
    marital_status = fields.Char('婚姻状况')

    # === 从业经历 ===
    entry_time = fields.Date('入职时间')
    working_date = fields.Date('工作年限起算日')
    career_years = fields.Integer('从业年限')
    guide_group = fields.Char('导游分组')
    group_type = fields.Char('团队类型偏好')
    shop_type = fields.Char('购物店类型偏好')
    guide_advantage = fields.Text('导游优势')
    guide_star = fields.Float('导游星级', digits=(2, 1), help='取值 0~5，允许 0.5 步进')
    grade = fields.Char('等级')
    recommend_class = fields.Char('推荐等级')
    area = fields.Char('服务区域')
    power_area = fields.Char('授权区域')
    birthday = fields.Date('生日')

    # === 结算信息 ===
    account_bank = fields.Char('开户行')
    account_name = fields.Char('结算账户名')
    account_no = fields.Char('结算银行卡号')
    loan_rate = fields.Float('借款利率', digits=(5, 2))
    cw_code = fields.Char('财务编码')

    # === 司机兼导游信息 ===
    driver_licence = fields.Char('驾照号', help='司机兼导游')
    driver_seat_num = fields.Integer('座位数', help='司机兼导游')
    driver_car_type = fields.Char('车型', help='司机兼导游')
    driver_car_name = fields.Char('车辆名称', help='司机兼导游')

    # === 状态与审核 ===
    active = fields.Boolean('启用状态', default=True, tracking=True)
    audit_chk = fields.Boolean('审核状态')
    audit_user = fields.Char('审核人')
    audit_brief = fields.Text('审核说明')
    audit_date = fields.Datetime('审核时间')

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')
    job_id = fields.Many2one('hr.job', string='职务', index=True,
                             help='职务（复用原生 hr.job，源易途 items_11 的 15 条职务）')

    # === 智能按钮计数（跨模块懒加载：tour_resource 先于 tour_accounting 加载，
    #     故不声明 One2many，改为运行时按 guide_id 反查计数）===
    loan_count = fields.Integer('借款单数', compute='_compute_loan_count')
    real_pay_count = fields.Integer('报账单数', compute='_compute_real_pay_count')

    _uniq_guide_code = models.Constraint(
        'unique(guide_code)',
        '导游证号已存在',
    )
    _uniq_employee_id = models.Constraint(
        'unique(employee_id)',
        '该员工已关联其他导游（1:1）',
    )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id and not self.name:
            self.name = self.partner_id.name

    @api.constrains('guide_star')
    def _check_guide_star(self):
        for rec in self:
            if rec.guide_star and (rec.guide_star < 0 or rec.guide_star > 5):
                raise ValidationError('导游星级必须在 0~5 之间')

    def action_audit_approve(self):
        """审核通过：导游身份证必填（结算/个税代扣/保险投保依赖完整身份证号）"""
        for rec in self:
            if not rec.id_num:
                raise ValidationError(
                    '导游 %s 未填写身份证号，无法审核通过（结算/个税代扣/保险投保依赖完整身份证号）' % rec.name)
            rec.write({
                'audit_chk': True,
                'audit_user': self.env.user.name,
                'audit_date': fields.Datetime.now(),
            })

    def _compute_loan_count(self):
        if 'tour.guide.loan' not in self.env:
            self.loan_count = 0
            return
        groups = self.env['tour.guide.loan'].read_group(
            [('guide_id', 'in', self.ids)], ['guide_id'], ['guide_id'])
        counts = {g['guide_id'][0]: g['guide_id_count'] for g in groups}
        for rec in self:
            rec.loan_count = counts.get(rec.id, 0)

    def _compute_real_pay_count(self):
        if 'hr.expense' not in self.env:
            self.real_pay_count = 0
            return
        groups = self.env['hr.expense'].read_group(
            [('x_guide_id', 'in', self.ids)], ['x_guide_id'], ['x_guide_id'])
        counts = {g['x_guide_id'][0]: g['x_guide_id_count'] for g in groups}
        for rec in self:
            rec.real_pay_count = counts.get(rec.id, 0)

    def action_view_employee(self):
        """跳转员工档案（hr.employee）。"""
        self.ensure_one()
        if not self.employee_id:
            return {
                'type': 'ir.actions.act_window',
                'name': '员工档案',
                'res_model': 'hr.employee',
                'view_mode': 'form',
                'context': {'default_name': self.name,
                            'default_department_id': self.department_id.id,
                            'default_company_id': self.company_id.id},
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': '员工档案',
            'res_model': 'hr.employee',
            'view_mode': 'form',
            'res_id': self.employee_id.id,
            'target': 'current',
        }

    def action_view_loans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '借款单',
            'res_model': 'tour.guide.loan',
            'view_mode': 'kanban,list,form',
            'domain': [('guide_id', '=', self.id)],
            'context': {'default_guide_id': self.id},
        }

    def action_view_real_pays(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '报账单',
            'res_model': 'hr.expense',
            'view_mode': 'list,form',
            'domain': [('x_guide_id', '=', self.id)],
            'context': {'default_x_guide_id': self.id},
        }
