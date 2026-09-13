# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TourPassenger(models.Model):
    _name = 'tour.passenger'
    _description = 'Tour Passenger'
    _order = 'booking_id, sequence, id'
    
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Booking Reference
    booking_id = fields.Many2one('tour.booking', string='Booking', required=True,
                                  ondelete='cascade', index=True)
    
    # Personal Information
    name = fields.Char(string='Full Name', required=True)
    first_name = fields.Char(string='First Name')
    last_name = fields.Char(string='Last Name')
    
    # Passenger Type
    passenger_type = fields.Selection([
        ('adult', 'Adult'),
        ('child', 'Child'),
        ('infant', 'Infant'),
    ], string='Passenger Type', required=True, default='adult')
    
    # Personal Details
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], string='Gender')
    
    date_of_birth = fields.Date(string='Date of Birth')
    age = fields.Integer(string='Age', compute='_compute_age', store=True)
    nationality_id = fields.Many2one('res.country', string='Nationality')
    
    # Contact Information
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    mobile = fields.Char(string='Mobile')
    
    # Identification
    id_type = fields.Selection([
        ('passport', 'Passport'),
        ('id_card', 'ID Card'),
        ('driver_license', 'Driver License'),
        ('other', 'Other'),
    ], string='ID Type')
    
    id_number = fields.Char(string='ID Number')
    id_expiry_date = fields.Date(string='ID Expiry Date')
    id_issue_country_id = fields.Many2one('res.country', string='ID Issue Country')
    
    # Passport Details (for international travel)
    passport_number = fields.Char(string='Passport Number')
    passport_expiry_date = fields.Date(string='Passport Expiry Date')
    passport_issue_country_id = fields.Many2one('res.country', string='Passport Issue Country')
    
    # Medical Information
    blood_group = fields.Selection([
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ], string='Blood Group')
    
    medical_conditions = fields.Text(string='Medical Conditions')
    allergies = fields.Text(string='Allergies')
    special_needs = fields.Text(string='Special Needs')
    
    # Dietary Requirements
    dietary_requirements = fields.Selection([
        ('none', 'None'),
        ('vegetarian', 'Vegetarian'),
        ('vegan', 'Vegan'),
        ('gluten_free', 'Gluten Free'),
        ('halal', 'Halal'),
        ('kosher', 'Kosher'),
        ('other', 'Other'),
    ], string='Dietary Requirements', default='none')
    
    dietary_notes = fields.Text(string='Dietary Notes')
    
    # Emergency Contact
    emergency_contact_name = fields.Char(string='Emergency Contact Name')
    emergency_contact_relation = fields.Char(string='Emergency Contact Relation')
    emergency_contact_phone = fields.Char(string='Emergency Contact Phone')
    
    # Room Assignment
    room_number = fields.Char(string='Room Number')
    room_sharing_with = fields.Char(string='Sharing Room With')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Image
    image = fields.Image(string='Photo')
    
    @api.depends('date_of_birth')
    def _compute_age(self):
        today = fields.Date.today()
        for record in self:
            if record.date_of_birth:
                record.age = (today - record.date_of_birth).days // 365
            else:
                record.age = 0
    
    @api.constrains('email')
    def _check_email(self):
        for record in self:
            if record.email and '@' not in record.email:
                raise ValidationError(_('Invalid email address.'))
    
    @api.onchange('first_name', 'last_name')
    def _onchange_name_parts(self):
        if self.first_name or self.last_name:
            self.name = f"{self.first_name or ''} {self.last_name or ''}".strip()

