# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class TourHotel(models.Model):
    _name = 'tour.hotel'
    _description = 'Tour Hotel'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    
    name = fields.Char(string='Hotel Name', required=True, tracking=True, translate=True)
    code = fields.Char(string='Hotel Code', copy=False)
    active = fields.Boolean(default=True, tracking=True)
    
    # Location
    location = fields.Char(string='Location', help='City, Country')
    address = fields.Char(string='Full Address')
    
    # Contact Information
    partner_id = fields.Many2one('res.partner', string='Partner')
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street2')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip = fields.Char(string='Zip')
    country_id = fields.Many2one('res.country', string='Country')
    
    phone = fields.Char(string='Phone')
    mobile = fields.Char(string='Mobile')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    
    # Hotel Details
    hotel_type = fields.Selection([
        ('1_star', '1 Star'),
        ('2_star', '2 Star'),
        ('3_star', '3 Star'),
        ('4_star', '4 Star'),
        ('5_star', '5 Star'),
        ('resort', 'Resort'),
        ('boutique', 'Boutique Hotel'),
        ('hostel', 'Hostel'),
        ('guest_house', 'Guest House'),
        ('apartment', 'Apartment'),
    ], string='Hotel Type', default='3_star')
    
    star_rating = fields.Integer(string='Star Rating', help='Hotel star rating (1-5)')
    rating = fields.Float(string='Rating', digits=(2, 1))
    
    # Check-in/Check-out
    check_in_time = fields.Float(string='Check-in Time', help='Check-in time in 24h format (e.g., 15.0 for 3:00 PM)')
    check_out_time = fields.Float(string='Check-out Time', help='Check-out time in 24h format (e.g., 12.0 for 12:00 PM)')
    
    # Room Types
    room_type_ids = fields.One2many('tour.hotel.room.type', 'hotel_id', string='Room Types')
    
    # Amenities
    amenity_ids = fields.Many2many('tour.hotel.amenity', string='Amenities')
    
    # Description
    description = fields.Html(string='Description', translate=True)
    
    # Images
    image_1920 = fields.Image(string='Image', max_width=1920, max_height=1920)
    image_512 = fields.Image(related='image_1920', max_width=512, max_height=512, store=True)
    
    # Pricing
    price_per_night = fields.Monetary(string='Price per Night', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                   default=lambda self: self.env.company.currency_id)
    
    # Product Link for invoicing
    product_id = fields.Many2one('product.product', string='Product',
                                  help='Product used for invoicing this hotel service')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Company
    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code('tour.hotel') or _('New')
        return super().create(vals_list)


class TourHotelRoomType(models.Model):
    _name = 'tour.hotel.room.type'
    _description = 'Hotel Room Type'
    _order = 'sequence, name'
    
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Room Type', required=True, translate=True)
    hotel_id = fields.Many2one('tour.hotel', string='Hotel', required=True, ondelete='cascade')
    description = fields.Text(string='Description', translate=True)
    capacity = fields.Integer(string='Capacity', default=2)
    price_per_night = fields.Monetary(string='Price per Night', currency_field='currency_id')
    currency_id = fields.Many2one(related='hotel_id.currency_id', string='Currency', readonly=True)
    image = fields.Image(string='Image')


class TourHotelAmenity(models.Model):
    _name = 'tour.hotel.amenity'
    _description = 'Hotel Amenity'
    _order = 'name'
    
    name = fields.Char(string='Amenity', required=True, translate=True)
    icon = fields.Char(string='Icon Class')
    active = fields.Boolean(default=True)

