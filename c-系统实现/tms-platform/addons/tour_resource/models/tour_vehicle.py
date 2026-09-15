# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourVehicle(models.Model):
    _name = 'tour.vehicle'
    _description = '车辆档案'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, licence'

    # === 车辆基本信息 ===
    name = fields.Char('车牌号', required=True, index=True, tracking=True)
    licence = fields.Char('执照号', required=True, index=True, copy=False,
                          help='全局唯一，同一车牌不可建两条车辆档案')
    licence_date = fields.Date('执照日期')
    licence_type = fields.Char('执照类型')
    buy_date = fields.Date('购车日期')
    seat_num = fields.Integer('正式座位数', required=True, help='如 51（51+2 中的正式座）')
    extra_seat = fields.Integer('加座数', help='如 2（51+2 中的加座），与正式座拆分存储以保留「51+2座」行业表达')
    car_type = fields.Char('车型')
    is_autarky = fields.Boolean('是否自营车辆')
    help_code = fields.Char('助记码', index=True)
    remark = fields.Text('备注')
    image_1920 = fields.Binary('图片')
    image_128 = fields.Binary('图片 128', related='image_1920')

    # === 关联司机 ===
    driver_id = fields.Many2one('tour.driver', string='关联司机', index=True,
                                ondelete='set null',
                                help='关联司机档案；司机信息（姓名/身份证/手机/结算）统一在司机档案管理')

    # === 所属车队 ===
    supplier_id = fields.Many2one('tour.supplier', string='所属车队（车辆公司）',
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

    @api.constrains('supplier_id')
    def _check_supplier_sup_type(self):
        for rec in self:
            if rec.supplier_id and rec.supplier_id.sup_type != 'vehicle_comp':
                raise ValidationError('车辆的所属车队必须为 sup_type=vehicle_comp 的供应商')
