# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.exceptions import AccessError


class TaCompanyMixin(models.AbstractModel):
    """SaaS 预留原则①：全部业务模型挂 company_id 并配 record rule。"""
    _name = 'ta.mixin'
    _description = 'Travel Agency Base Mixin'

    company_id = fields.Many2one(
        'res.company', string='公司', required=True, index=True,
        default=lambda self: self.env.company)

    def _ta_check_company(self):
        if any(rec.company_id != self.env.company for rec in self):
            raise AccessError("不允许跨公司操作系统数据。")
