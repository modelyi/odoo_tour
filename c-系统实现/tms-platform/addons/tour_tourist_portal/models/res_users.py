# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_tourist = fields.Boolean(
        string='游客门户',
        compute='_compute_is_tourist',
        inverse='_inverse_is_tourist',
        help='标记用户是否为游客门户用户，可访问游客门户'
    )

    def _compute_is_tourist(self):
        """计算是否为游客门户用户"""
        tourist_group = self.env.ref(
            'tour_tourist_portal.group_tourist_portal', raise_if_not_found=False)
        for user in self:
            if tourist_group:
                user.is_tourist = tourist_group in user.group_ids
            else:
                user.is_tourist = False

    def _inverse_is_tourist(self):
        """设置游客门户角色"""
        tourist_group = self.env.ref(
            'tour_tourist_portal.group_tourist_portal', raise_if_not_found=False)
        if not tourist_group:
            return
        for user in self:
            if user.is_tourist:
                user.write({'group_ids': [(4, tourist_group.id)]})
            else:
                user.write({'group_ids': [(3, tourist_group.id)]})
