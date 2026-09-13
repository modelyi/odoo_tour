# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class TourTransportation(models.Model):
    _name = 'tour.transportation'
    _description = 'Tour Transportation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    
    name = fields.Char(string='Transportation Name', required=True, tracking=True, translate=True)
    code = fields.Char(string='Code', copy=False)
    active = fields.Boolean(default=True, tracking=True)
    
    # Transportation Details
    transport_type = fields.Selection([
        ('bus', 'Bus'),
        ('car', 'Car'),
        ('van', 'Van'),
        ('train', 'Train'),
        ('flight', 'Flight'),
        ('boat', 'Boat'),
        ('cruise', 'Cruise'),
        ('bicycle', 'Bicycle'),
        ('walking', 'Walking'),
        ('other', 'Other'),
    ], string='Type', required=True, default='bus')
    
    vehicle_model = fields.Char(string='Vehicle Model')
    vehicle_number = fields.Char(string='Vehicle Number')
    capacity = fields.Integer(string='Capacity')
    
    # Pricing
    cost_per_unit = fields.Monetary(string='Cost per Unit', currency_field='currency_id',
                                     help='Cost per unit (per day, per trip, etc.)')
    
    # Provider Information
    partner_id = fields.Many2one('res.partner', string='Transportation Provider')
    driver_name = fields.Char(string='Driver Name')
    driver_phone = fields.Char(string='Driver Phone')
    driver_license = fields.Char(string='Driver License')
    
    # Description
    description = fields.Html(string='Description', translate=True)
    features = fields.Text(string='Features', translate=True)
    
    # Image
    image_1920 = fields.Image(string='Image', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)
    
    # Pricing
    price_per_day = fields.Monetary(string='Price per Day', currency_field='currency_id')
    price_per_km = fields.Monetary(string='Price per KM', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                   default=lambda self: self.env.company.currency_id)
    
    # Product Link for invoicing
    product_id = fields.Many2one('product.product', string='Product',
                                  help='Product used for invoicing this transportation service')
    
    # Amenities
    has_ac = fields.Boolean(string='Air Conditioning', default=True)
    has_wifi = fields.Boolean(string='WiFi')
    has_tv = fields.Boolean(string='TV/Entertainment')
    has_restroom = fields.Boolean(string='Restroom')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Company
    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('tour.transportation') or _('New')
        return super().create(vals_list)

