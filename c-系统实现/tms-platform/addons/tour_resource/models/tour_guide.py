# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourGuide(models.Model):
    _name = 'tour.guide'
    _description = '导游档案'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.encrypted.field.mixin']
    _order = 'name, guide_code'

    # 敏感字段（AES-256-GCM 落盘加密 + 掩码展示 + 等值检索散列）
    _encrypted_fields = {'id_num': True, 'account_no': True}

    # === 基本信息 ===
    name = fields.Char('导游姓名', required=True, index=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='关联联系人', index=True,
                                 help='导游的个人联系人档案，可关联 res.users 统一用户体系')
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
    id_num = fields.Char('身份证号',
                         help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码。审核通过时必填')
    id_num_hash = fields.Char('身份证号检索散列', index=True, copy=False,
                              help='HMAC-SHA256 等值检索辅助列（不存明文），用于精确匹配搜索')
    id_num_masked = fields.Char('身份证号掩码', compute='_compute_masked_fields',
                                help='界面/报表/日志/导出默认显示 ****后4位')
    tel = fields.Char('固定电话', help='🟡 敏感字段：界面掩码')
    mobile = fields.Char('手机号', help='🟡 敏感字段：界面掩码')
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
    account_no = fields.Char('结算银行卡号', help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码')
    account_no_hash = fields.Char('结算银行卡号检索散列', index=True, copy=False,
                                  help='HMAC-SHA256 等值检索辅助列（不存明文）')
    account_no_masked = fields.Char('结算银行卡号掩码', compute='_compute_masked_fields',
                                    help='界面/报表/日志/导出默认显示 ****后4位')
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

    _uniq_guide_code = models.Constraint(
        'unique(guide_code)',
        '导游证号已存在',
    )

    @api.depends('id_num', 'account_no')
    def _compute_masked_fields(self):
        for rec in self:
            rec.id_num_masked = rec._encrypt_mask('id_num')
            rec.account_no_masked = rec._encrypt_mask('account_no')

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
