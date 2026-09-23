# -*- coding: utf-8 -*-
from odoo import models, fields


class TourBank(models.Model):
    """Replaces the upstream model res.bank, which no longer exists in Odoo 20."""
    _name = 'tour.bank'
    _description = '开户行'
    _order = 'name'

    name = fields.Char('银行名称', required=True, index=True)
    bic = fields.Char('BIC/SWIFT', index=True)
    active = fields.Boolean(default=True)
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    phone = fields.Char()
    email = fields.Char()
    country = fields.Many2one('res.country', string='国家')
    state = fields.Many2one('res.country.state', string='省份')
