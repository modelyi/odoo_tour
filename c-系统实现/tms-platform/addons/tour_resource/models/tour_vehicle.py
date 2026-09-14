# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourVehicle(models.Model):
    _name = 'tour.vehicle'
    _description = '车辆档案'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tour.encrypted.field.mixin']
    _order = 'name, licence'

    # 敏感字段（AES-256-GCM 落盘加密 + 掩码展示 + 等值检索散列）
    _encrypted_fields = {'id_num': True, 'bank_account': True}

    # === 车辆基本信息 ===
    name = fields.Char('车牌号', required=True, index=True, tracking=True)
    driver_name = fields.Char('司机姓名', required=True, index=True)
    driver_code = fields.Char('司机编码')
    help_code = fields.Char('助记码', index=True)
    sex = fields.Selection([
        ('male', '男'),
        ('female', '女'),
    ], string='性别')
    nation = fields.Char('民族')
    born_place = fields.Char('出生地')
    edu = fields.Char('学历')
    id_num = fields.Char('司机身份证号', help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码')
    id_num_hash = fields.Char('身份证号检索散列', index=True, copy=False,
                              help='HMAC-SHA256 等值检索辅助列（不存明文）')
    id_num_masked = fields.Char('身份证号掩码', compute='_compute_masked_fields',
                                help='界面/报表/日志/导出默认显示 ****后4位')
    age = fields.Integer('年龄')
    tel = fields.Char('固定电话', help='🟡 敏感字段：界面掩码')
    mobile = fields.Char('手机号', help='🟡 敏感字段：界面掩码')
    zip_code = fields.Char('邮编')
    addr = fields.Char('地址')
    photo = fields.Binary('照片')
    photo2 = fields.Binary('照片2')
    remark = fields.Text('备注')

    # === 车辆证照 ===
    licence = fields.Char('执照号', required=True, index=True, copy=False,
                          help='全局唯一，同一车牌不可建两条车辆档案')
    licence_date = fields.Date('驾照日期')
    licence_type = fields.Char('驾照类型')
    buy_date = fields.Date('购车日期')
    seat_num = fields.Integer('正式座位数', required=True, help='如 51（51+2 中的正式座）')
    extra_seat = fields.Integer('加座数', help='如 2（51+2 中的加座），与正式座拆分存储以保留「51+2座」行业表达')
    car_type = fields.Char('车型')
    is_autarky = fields.Boolean('是否自营车辆')

    # === 结算信息 ===
    loan_rate = fields.Float('借款利率', digits=(5, 2))
    opening_bank = fields.Char('开户行')
    bank_account = fields.Char('司机银行账号', help='🔴 敏感字段：已 AES-256-GCM 加密存储，界面掩码')
    bank_account_hash = fields.Char('银行账号检索散列', index=True, copy=False,
                                    help='HMAC-SHA256 等值检索辅助列（不存明文）')
    bank_account_masked = fields.Char('银行账号掩码', compute='_compute_masked_fields',
                                      help='界面/报表/日志/导出默认显示 ****后4位')

    # === 所属车队 ===
    supplier_id = fields.Many2one('res.partner', string='所属车队（车辆公司）',
                                  index=True, domain=[('sup_type', '=', 'vehicle_comp')])
    supplier_name = fields.Char('车队名称冗余')
    power_area = fields.Char('授权区域')
    cw_code = fields.Char('财务编码')

    # === 状态与审核 ===
    active = fields.Boolean('启用状态', default=True, tracking=True)
    audit_chk = fields.Boolean('审核状态', default=True)
    audit_user = fields.Char('审核人')
    audit_brief = fields.Text('审核说明')
    audit_date = fields.Datetime('审核时间')

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    _uniq_vehicle_licence = models.Constraint(
        'unique(licence)',
        '车牌号已存在',
    )

    @api.depends('id_num', 'bank_account')
    def _compute_masked_fields(self):
        for rec in self:
            rec.id_num_masked = rec._encrypt_mask('id_num')
            rec.bank_account_masked = rec._encrypt_mask('bank_account')

    @api.constrains('supplier_id')
    def _check_supplier_sup_type(self):
        for rec in self:
            if rec.supplier_id and rec.supplier_id.sup_type != 'vehicle_comp':
                raise ValidationError('车辆的所属车队必须为 sup_type=vehicle_comp 的供应商')
