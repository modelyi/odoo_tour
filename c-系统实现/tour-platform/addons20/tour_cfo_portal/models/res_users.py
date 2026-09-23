# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_cfo = fields.Boolean(
        string='CFO 角色',
        compute='_compute_is_cfo',
        inverse='_inverse_is_cfo',
        help='标记用户是否为 CFO 角色，可访问 CFO 门户'
    )

    def _compute_is_cfo(self):
        """计算是否为 CFO 角色"""
        cfo_group = self.env.ref('tour_cfo_portal.group_cfo_portal', raise_if_not_found=False)
        for user in self:
            if cfo_group:
                user.is_cfo = cfo_group in user.group_ids
            else:
                user.is_cfo = False

    def _inverse_is_cfo(self):
        """设置 CFO 角色"""
        cfo_group = self.env.ref('tour_cfo_portal.group_cfo_portal', raise_if_not_found=False)
        if not cfo_group:
            return
        for user in self:
            if user.is_cfo:
                user.write({'group_ids': [(4, cfo_group.id)]})
            else:
                user.write({'group_ids': [(3, cfo_group.id)]})
