# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    licence = fields.Char('执照号', copy=False, index=True,
                          help='全局唯一，同一车牌不可建两条车辆档案')
    seat_num = fields.Integer('正式座位数', help='如 51（51+2 中的正式座）')
    extra_seat = fields.Integer('加座数', help='如 2（51+2 中的加座），与正式座拆分存储以保留「51+2座」行业表达')
    is_autarky = fields.Boolean('自营车辆')

    tour_driver_id = fields.Many2one('tour.driver', string='旅行社司机', index=True,
                                     ondelete='set null',
                                     help='关联旅行社司机档案')
    tour_supplier_id = fields.Many2one('tour.supplier', string='所属车队',
                                       index=True,
                                       domain=[('sup_type', '=', 'vehicle_comp')],
                                       help='所属车队（车辆公司），必须为 sup_type=vehicle_comp 的供应商')

    help_code = fields.Char('助记码', index=True)
    power_area = fields.Char('授权区域')
    cw_code = fields.Char('财务编码')
    licence_date = fields.Date('执照日期')
    licence_type = fields.Char('执照类型')

    audit_chk = fields.Boolean('审核状态', default=True)
    audit_user = fields.Char('审核人')
    audit_brief = fields.Text('审核说明')
    audit_date = fields.Datetime('审核时间')

    department_id = fields.Many2one('hr.department', string='所属部门')

    _uniq_licence = models.Constraint(
        'unique(licence)', '执照号已存在',
    )

    @api.constrains('tour_supplier_id')
    def _check_supplier_sup_type(self):
        for rec in self:
            if rec.tour_supplier_id and rec.tour_supplier_id.sup_type != 'vehicle_comp':
                raise ValidationError('所属车队必须为 sup_type=vehicle_comp 的供应商')

    def action_audit_approve(self):
        for rec in self:
            rec.write({
                'audit_chk': True,
                'audit_user': self.env.user.name,
                'audit_date': fields.Datetime.now(),
            })
