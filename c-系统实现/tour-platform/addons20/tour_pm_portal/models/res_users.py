# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_pm = fields.Boolean(
        string='产品专家',
        compute='_compute_is_pm',
        inverse='_inverse_is_pm',
        help='标记用户是否为产品专家角色，可访问产品门户'
    )

    def _compute_is_pm(self):
        pm_group = self.env.ref(
            'tour_pm_portal.group_pm_portal', raise_if_not_found=False)
        for user in self:
            if pm_group:
                user.is_pm = pm_group in user.group_ids
            else:
                user.is_pm = False

    def _inverse_is_pm(self):
        pm_group = self.env.ref(
            'tour_pm_portal.group_pm_portal', raise_if_not_found=False)
        if not pm_group:
            return
        for user in self:
            if user.is_pm:
                user.write({'group_ids': [(4, pm_group.id)]})
            else:
                user.write({'group_ids': [(3, pm_group.id)]})
