# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    """批6 P0-6：收入成本确认的公司级配置（不同公司可不同做法，BS-14 + BS-10 §7.2）。"""
    _inherit = 'res.company'

    TAXPAYER = [
        ('general', '一般纳税人'),
        ('small_scale', '小规模纳税人'),
    ]

    ta_taxpayer_type = fields.Selection(
        TAXPAYER, string='纳税人身份', default='general',
        help='决定收入确认的默认增值税率：一般纳税人 6%、小规模纳税人 3%（可手改 ta_vat_rate）。')
    ta_vat_rate = fields.Float(
        string='收入增值税率', default=0.06, digits=(12, 6),
        help='收入确认时对含税口径订单金额的拆税率（小数，如 0.06）。'
             '0 表示不拆税（全额进收入）。')
    ta_revenue_dd_split_tax = fields.Boolean(
        string='41 代订差价拆销项税', default=False,
        help='产品口径：差价销项税随开票体系（BS-12）计提，默认差价含税全额进 6001.03；'
             '勾选后按 ta_vat_rate 拆分销项税。')
    ta_revenue_auto_on_depart = fields.Boolean(
        string='发团自动确认收入', default=True,
        help='勾选后发团动作自动生成收入确认凭证（发团日口径，BS-10 §7.2）；'
             '不勾选则仅在发团表单手动点击「确认收入」。')
