# -*- coding: utf-8 -*-
"""res.partner 标准字段扩展。

Odoo 19 将 res.partner.name 的标准定义改为不可翻译
（源码：name = fields.Char(index=True, default_export_compatible=True)），
导致公司等联系人无法通过翻译机制保存多语言名称。

这里在原字段基础上仅追加 translate=True，保留 index / default_export_compatible
等标准属性，恢复 name 的多语言翻译能力（含 res.company.name 的同步）。
"""
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    name = fields.Char(
        index=True,
        default_export_compatible=True,
        translate=True,
    )
