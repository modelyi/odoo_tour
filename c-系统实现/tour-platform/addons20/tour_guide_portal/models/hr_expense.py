# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrExpense(models.Model):
    _inherit = ['hr.expense', 'portal.mixin']
    _name = 'hr.expense'

    @api.depends('name')
    def _compute_access_url(self):
        for rec in self:
            rec.access_url = '/my/guide/expenses/%s' % rec.id

    def _compute_access_warning(self):
        super()._compute_access_warning()
        for rec in self:
            if rec.state == 'draft':
                rec.access_warning = '报账单待提交，门户可继续编辑。'
