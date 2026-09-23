# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourCommission(models.Model):
    _inherit = ['tour.commission', 'portal.mixin']
    _name = 'tour.commission'

    @api.depends('name')
    def _compute_access_url(self):
        for rec in self:
            rec.access_url = '/my/guide/commissions/%s' % rec.id

    def _compute_access_warning(self):
        super()._compute_access_warning()
        for rec in self:
            if rec.state == 'draft':
                rec.access_warning = '佣金尚未确认，门户仅展示待确认状态。'
