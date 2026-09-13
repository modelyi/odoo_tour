# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TourBookingWizard(models.TransientModel):
    _name = 'tour.booking.wizard'
    _description = 'Tour Booking Wizard'
    
    inquiry_id = fields.Many2one('tour.inquiry', string='Related Inquiry')
    package_id = fields.Many2one('tour.package', string='Tour Package', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    
    travel_start_date = fields.Date(string='Travel Start Date', required=True)
    preferred_date = fields.Date(string='Preferred Date', 
                                  help='Preferred travel date from inquiry')
    
    num_adults = fields.Integer(string='Adults', default=1, required=True)
    num_children = fields.Integer(string='Children', default=0)
    num_infants = fields.Integer(string='Infants', default=0)
    
    customer_notes = fields.Text(string='Customer Notes')
    special_requirements = fields.Text(string='Special Requirements')
    
    @api.onchange('preferred_date')
    def _onchange_preferred_date(self):
        """Set travel start date from preferred date"""
        if self.preferred_date and not self.travel_start_date:
            self.travel_start_date = self.preferred_date
    
    def action_create_booking(self):
        """Create booking from wizard"""
        self.ensure_one()
        
        booking_vals = {
            'package_id': self.package_id.id,
            'partner_id': self.partner_id.id,
            'travel_start_date': self.travel_start_date,
            'num_adults': self.num_adults,
            'num_children': self.num_children,
            'num_infants': self.num_infants,
            'customer_notes': self.customer_notes,
            'special_requirements': self.special_requirements,
            'inquiry_id': self.inquiry_id.id if self.inquiry_id else False,
            'state': 'draft',
        }
        
        # Copy data from inquiry if available
        if self.inquiry_id:
            booking_vals.update({
                'source': self.inquiry_id.source,
                'user_id': self.inquiry_id.user_id.id if self.inquiry_id.user_id else self.env.user.id,
                'team_id': self.inquiry_id.team_id.id if self.inquiry_id.team_id else False,
            })
        
        booking = self.env['tour.booking'].create(booking_vals)
        
        # Update inquiry state if exists
        if self.inquiry_id:
            self.inquiry_id.write({
                'state': 'converted',
                'booking_id': booking.id,
            })
            
            # Update related CRM lead
            if self.inquiry_id.lead_id:
                self.inquiry_id.lead_id.message_post(
                    body=_('Converted to Booking: %s', booking.name)
                )
        
        # Return action to open the booking
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tour Booking'),
            'res_model': 'tour.booking',
            'res_id': booking.id,
            'view_mode': 'form',
            'target': 'current',
        }

