# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class TourAttraction(models.Model):
    _name = 'tour.attraction'
    _description = 'Tour Attraction'
    _inherit = ['mail.thread']
    _order = 'name'
    
    name = fields.Char(string='Attraction Name', required=True, translate=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    
    # Location
    location = fields.Char(string='Location', help='City, Country')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    country_id = fields.Many2one('res.country', string='Country')
    address = fields.Text(string='Address')
    
    # GPS Coordinates
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    
    # Attraction Details
    attraction_type = fields.Selection([
        ('historical', 'Historical Site'),
        ('museum', 'Museum'),
        ('park', 'Park/Garden'),
        ('beach', 'Beach'),
        ('mountain', 'Mountain'),
        ('religious', 'Religious Site'),
        ('entertainment', 'Entertainment'),
        ('shopping', 'Shopping'),
        ('wildlife', 'Wildlife'),
        ('adventure', 'Adventure Activity'),
        ('cultural', 'Cultural'),
        ('other', 'Other'),
    ], string='Type', required=True, default='other')
    
    # Description
    description = fields.Html(string='Description', translate=True)
    highlights = fields.Text(string='Highlights', translate=True)
    
    # Operating Hours
    opening_time = fields.Float(string='Opening Time')
    closing_time = fields.Float(string='Closing Time')
    opening_days = fields.Char(string='Opening Days')
    
    # Images
    image_1920 = fields.Image(string='Main Image', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)
    
    # Pricing
    entry_fee = fields.Monetary(string='Entry Fee', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                   default=lambda self: self.env.company.currency_id)
    
    # Product Link for invoicing
    product_id = fields.Many2one('product.product', string='Product',
                                  help='Product used for invoicing this attraction')
    
    # Rating
    rating = fields.Float(string='Rating', digits=(2, 1))
    
    # Contact
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    
    # Duration
    duration = fields.Float(string='Duration (hours)', digits=(4, 1),
                            help='Expected visit duration in hours')
    recommended_duration = fields.Float(string='Recommended Duration (hours)', digits=(4, 1))
    
    # Notes
    notes = fields.Text(string='Notes')
    tips = fields.Text(string='Visitor Tips', translate=True)
    
    # Company
    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)

