# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_tourist = fields.Boolean(
        '游客门户',
        compute='_compute_is_tourist',
        inverse='_inverse_is_tourist',
        help='标记此联系人是否为游客门户用户')
    tourist_reg_ids = fields.One2many(
        'tour.plan.reg', 'partner_id', string='报名记录')

    def _compute_is_tourist(self):
        tourist_group = self.env.ref(
            'tour_tourist_portal.group_tourist_portal', raise_if_not_found=False)
        for partner in self:
            if tourist_group and partner.user_ids:
                partner.is_tourist = any(
                    tourist_group in u.group_ids for u in partner.user_ids)
            else:
                partner.is_tourist = False

    def _inverse_is_tourist(self):
        tourist_group = self.env.ref(
            'tour_tourist_portal.group_tourist_portal', raise_if_not_found=False)
        if not tourist_group:
            return
        for partner in self:
            for user in partner.user_ids:
                if partner.is_tourist:
                    user.write({'group_ids': [(4, tourist_group.id)]})
                else:
                    user.write({'group_ids': [(3, tourist_group.id)]})
