# -*- coding: utf-8 -*-
"""tour.plan 扩展：订单来源追加「7 电商」渠道。"""
from odoo import fields, models


class TourPlan(models.Model):
    _inherit = 'tour.plan'

    from_type = fields.Selection(
        selection_add=[('7', '电商')])
