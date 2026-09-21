# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourGuide(models.Model):
    _inherit = 'tour.guide'

    portal_user_id = fields.Many2one(
        'res.users', string='门户用户', compute='_compute_portal_user_id',
        store=True, help='通过 partner_id 关联的门户登录用户')
    has_portal_access = fields.Boolean(
        '已开通门户', compute='_compute_portal_user_id', store=True)

    @api.depends('partner_id')
    def _compute_portal_user_id(self):
        Users = self.env['res.users'].sudo()
        for guide in self:
            if guide.partner_id:
                user = Users.search([
                    ('partner_id', '=', guide.partner_id.id),
                    ('share', '=', True),
                ], limit=1)
                guide.portal_user_id = user.id
                guide.has_portal_access = bool(user)
            else:
                guide.portal_user_id = False
                guide.has_portal_access = False

    def action_send_portal_invitation(self):
        """向导游发送门户激活邮件：确保存在 portal 用户，然后发送邀请。"""
        self.ensure_one()
        if not self.partner_id:
            return
        Users = self.env['res.users'].sudo()
        user = Users.search([
            ('partner_id', '=', self.partner_id.id),
            ('share', '=', True),
        ], limit=1)
        if not user:
            user = Users.with_context(no_reset_password=True).create({
                'name': self.name,
                'login': self.partner_id.email or self.guide_code,
                'partner_id': self.partner_id.id,
                'share': True,
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            })
        template = self.env.ref(
            'tour_guide_portal.mail_template_guide_portal_invite',
            raise_if_not_found=False)
        if template:
            template.with_context(
                lang=self.partner_id.lang,
                portal_url='/my/guide',
            ).send_mail(self.id, force_send=True)
