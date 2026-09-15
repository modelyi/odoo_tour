# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourDriver(models.Model):
    _name = 'tour.driver'
    _description = '司机档案'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # === 身份底座：res.partner（独立，不依赖 hr.employee）===
    partner_id = fields.Many2one('res.partner', string='关联联系人', index=True,
                                 ondelete='set null',
                                 help='司机的身份联系人；内部司机可关联员工 work_contact，外部司机可关联任意 partner')

    # === 劳动关系（可选：内部司机挂员工，外部司机不挂）===
    employee_id = fields.Many2one('hr.employee', string='员工档案', index=True,
                                  ondelete='set null',
                                  help='司机的劳动关系档案；1:1 司机↔员工')

    # === 导游关联（可选：司机兼导游时关联）===
    guide_id = fields.Many2one('tour.guide', string='导游档案', index=True,
                               ondelete='set null',
                               help='司机兼导游时关联导游档案')

    # === 基本信息 ===
    name = fields.Char('司机姓名', required=True, index=True, tracking=True)
    driver_code = fields.Char('司机编码', index=True)
    help_code = fields.Char('助记码', index=True)
    sex = fields.Selection([
        ('male', '男'),
        ('female', '女'),
    ], string='性别')
    nation = fields.Char('民族')
    born_place = fields.Char('出生地')
    edu = fields.Char('学历')
    id_num = fields.Char('身份证号')
    age = fields.Integer('年龄')
    tel = fields.Char('固定电话')
    mobile = fields.Char('手机号')
    zip_code = fields.Char('邮编')
    addr = fields.Char('地址')
    photo = fields.Binary('照片')
    remark = fields.Text('备注')

    # === 驾驶资质 ===
    licence_type = fields.Char('准驾车型')
    driver_licence = fields.Char('驾驶证号')

    # === 结算信息 ===
    loan_rate = fields.Float('借款利率', digits=(5, 2))
    opening_bank = fields.Char('开户行')
    bank_account = fields.Char('银行账号')
    cw_code = fields.Char('财务编码')

    # === 状态 ===
    active = fields.Boolean('启用状态', default=True, tracking=True)

    # === 归属 ===
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='所属部门')

    _uniq_employee_id = models.Constraint(
        'unique(employee_id)',
        '该员工已关联其他司机（1:1）',
    )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id and not self.name:
            self.name = self.partner_id.name

    @api.constrains('loan_rate')
    def _check_loan_rate(self):
        for rec in self:
            if rec.loan_rate and rec.loan_rate < 0:
                raise ValidationError('借款利率不能为负数')
