# -*- coding: utf-8 -*-
from odoo import models, fields


class HrEmployee(models.Model):
    # 扩展 hr.employee（显式 _name 等于被扩展模型，避免类名被自动转成新模型）
    _name = 'hr.employee'
    _inherit = 'hr.employee'

    # 用工类型：财务人事线（借款/报销/佣金个税）据此区分「工资薪金」与「劳务报酬」
    employment_type = fields.Selection([
        ('labor_contract', '劳动合同'),
        ('service_contract', '劳务协议/挂靠'),
        ('temporary', '临时'),
    ], string='用工类型', default='service_contract', index=True, tracking=True,
       help='劳动合同 → 工资薪金个税；劳务协议/挂靠、临时 → 劳务报酬个税')
