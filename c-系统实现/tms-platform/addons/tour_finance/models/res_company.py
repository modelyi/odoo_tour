# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    tour_taxpayer_type = fields.Selection([
        ('general', '一般纳税人'),
        ('small', '小规模纳税人'),
    ], string='纳税人身份', default='general', required=True,
       help='决定增值税税率/征收率与计税分录口径 [BS-11 §三]')

    tour_vat_rate = fields.Float('增值税税率(%)', default=6.0, digits=(5, 2),
        help='一般纳税人税率，旅游服务默认 6% [财税2016-36号]')

    tour_vat_levy_rate = fields.Float('征收率(%)', default=3.0, digits=(5, 2),
        help='小规模征收率，默认 3%，优惠期减按 1% [财政部税务总局公告2023年第19号]')

    tour_diff_tax_enabled = fields.Boolean('启用差额征税', default=True,
        help='[财税2016-36号] 选择差额征税后 36 个月不得变更；'
             '关闭则走全额计税，不生成销项税额抵减分录')
