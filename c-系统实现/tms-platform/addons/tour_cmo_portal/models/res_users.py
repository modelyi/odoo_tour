# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_cmo = fields.Boolean(
        string='CMO 角色',
        compute='_compute_is_cmo',
        inverse='_inverse_is_cmo',
        help='标记用户是否为 CMO 角色，可访问增长官门户'
    )

    def _compute_is_cmo(self):
        """计算是否为 CMO 角色"""
        cmo_group = self.env.ref(
            'tour_cmo_portal.group_cmo_portal', raise_if_not_found=False)
        for user in self:
            if cmo_group:
                user.is_cmo = cmo_group in user.group_ids
            else:
                user.is_cmo = False

    def _inverse_is_cmo(self):
        """设置 CMO 角色"""
        cmo_group = self.env.ref(
            'tour_cmo_portal.group_cmo_portal', raise_if_not_found=False)
        if not cmo_group:
            return
        for user in self:
            if user.is_cmo:
                user.write({'group_ids': [(4, cmo_group.id)]})
            else:
                user.write({'group_ids': [(3, cmo_group.id)]})
