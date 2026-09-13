# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class TourMeal(models.Model):
    _name = 'tour.meal'
    _description = 'Tour Meal'
    _order = 'name'
    
    name = fields.Char(string='Meal Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    
    # Meal Type
    meal_type = fields.Selection([
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('snack', 'Snack'),
        ('beverage', 'Beverage'),
        ('full_board', 'Full Board'),
        ('half_board', 'Half Board'),
    ], string='Meal Type', required=True, default='breakfast')
    
    # Description
    description = fields.Html(string='Description', translate=True)
    menu = fields.Text(string='Menu', translate=True)
    
    # Dietary Options
    dietary_options = fields.Text(string='Dietary Options', translate=True,
                                   help='Available dietary options (e.g., Vegetarian, Vegan, Gluten-Free)')
    is_vegetarian = fields.Boolean(string='Vegetarian')
    is_vegan = fields.Boolean(string='Vegan')
    is_gluten_free = fields.Boolean(string='Gluten Free')
    is_halal = fields.Boolean(string='Halal')
    is_kosher = fields.Boolean(string='Kosher')
    
    # Restaurant Information
    restaurant_name = fields.Char(string='Restaurant Name')
    partner_id = fields.Many2one('res.partner', string='Restaurant Partner')
    
    # Image
    image = fields.Image(string='Image')
    
    # Pricing
    price = fields.Monetary(string='Price', currency_field='currency_id')
    cost_per_person = fields.Monetary(string='Cost per Person', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                   default=lambda self: self.env.company.currency_id)
    
    # Product Link for invoicing
    product_id = fields.Many2one('product.product', string='Product',
                                  help='Product used for invoicing this meal service')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Company
    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)

