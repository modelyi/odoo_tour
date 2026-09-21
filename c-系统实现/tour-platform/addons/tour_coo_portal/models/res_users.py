# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_coo = fields.Boolean(
        string='COO 角色',
        compute='_compute_is_coo',
        inverse='_inverse_is_coo',
        help='标记用户是否为 COO 角色，可访问运营门户'
    )

    def _compute_is_coo(self):
        """计算是否为 COO 角色"""
        coo_group = self.env.ref(
            'tour_coo_portal.group_coo_portal', raise_if_not_found=False)
        for user in self:
            if coo_group:
                user.is_coo = coo_group in user.group_ids
            else:
                user.is_coo = False

    def _inverse_is_coo(self):
        """设置 COO 角色"""
        coo_group = self.env.ref(
            'tour_coo_portal.group_coo_portal', raise_if_not_found=False)
        if not coo_group:
            return
        for user in self:
            if user.is_coo:
                user.write({'group_ids': [(4, coo_group.id)]})
            else:
                user.write({'group_ids': [(3, coo_group.id)]})
