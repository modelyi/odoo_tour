# -*- coding: utf-8 -*-
from odoo import models, fields, api


class TourGuideLoan(models.Model):
    _inherit = ['tour.guide.loan', 'portal.mixin']
    _name = 'tour.guide.loan'

    @api.depends('name')
    def _compute_access_url(self):
        for rec in self:
            rec.access_url = '/my/guide/loans/%s' % rec.id

    def _compute_access_warning(self):
        super()._compute_access_warning()
        for rec in self:
            if rec.state == 'draft':
                rec.access_warning = '借款单待审批，门户仅展示状态信息。'
