# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'
    
    # Tour Agency Settings
    tour_auto_create_lead = fields.Boolean(
        string='Auto Create CRM Lead from Inquiry',
        default=True,
        help='Automatically create a CRM lead when a tour inquiry is submitted'
    )
    tour_create_sale_order = fields.Boolean(
        string='Auto Create Sales Order from Booking',
        default=True,
        help='Automatically create a sales order when a booking is confirmed'
    )
    tour_create_calendar_event = fields.Boolean(
        string='Create Calendar Event for Bookings',
        default=True,
        help='Automatically create calendar events for tour bookings'
    )
    tour_require_payment = fields.Boolean(
        string='Require Payment for Booking',
        default=False,
        help='Require full or partial payment to confirm booking'
    )
    tour_minimum_payment_percent = fields.Float(
        string='Minimum Payment Percentage',
        default=0.0,
        help='Minimum payment percentage required to confirm booking (0-100)'
    )
    tour_cancellation_days = fields.Integer(
        string='Cancellation Notice Days',
        default=7,
        help='Minimum days notice required for cancellation'
    )
    tour_cancellation_fee_percent = fields.Float(
        string='Cancellation Fee Percentage',
        default=10.0,
        help='Cancellation fee as percentage of total amount'
    )
    tour_auto_confirm_booking = fields.Boolean(
        string='Auto Confirm Bookings',
        default=False,
        help='Automatically confirm bookings after payment'
    )
    tour_default_terms = fields.Html(
        string='Default Terms & Conditions',
        translate=True,
        help='Default terms and conditions for tour packages'
    )
    tour_default_cancellation_policy = fields.Html(
        string='Default Cancellation Policy',
        translate=True,
        help='Default cancellation policy for tour packages'
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    tour_auto_create_lead = fields.Boolean(
        related='company_id.tour_auto_create_lead',
        readonly=False,
        string='Auto Create CRM Lead from Inquiry'
    )
    tour_create_sale_order = fields.Boolean(
        related='company_id.tour_create_sale_order',
        readonly=False,
        string='Auto Create Sales Order from Booking'
    )
    tour_create_calendar_event = fields.Boolean(
        related='company_id.tour_create_calendar_event',
        readonly=False,
        string='Create Calendar Event for Bookings'
    )
    tour_require_payment = fields.Boolean(
        related='company_id.tour_require_payment',
        readonly=False,
        string='Require Payment for Booking'
    )
    tour_minimum_payment_percent = fields.Float(
        related='company_id.tour_minimum_payment_percent',
        readonly=False,
        string='Minimum Payment Percentage'
    )
    tour_cancellation_days = fields.Integer(
        related='company_id.tour_cancellation_days',
        readonly=False,
        string='Cancellation Notice Days'
    )
    tour_cancellation_fee_percent = fields.Float(
        related='company_id.tour_cancellation_fee_percent',
        readonly=False,
        string='Cancellation Fee Percentage'
    )
    tour_auto_confirm_booking = fields.Boolean(
        related='company_id.tour_auto_confirm_booking',
        readonly=False,
        string='Auto Confirm Bookings'
    )
    tour_default_terms = fields.Html(
        related='company_id.tour_default_terms',
        readonly=False,
        string='Default Terms & Conditions'
    )
    tour_default_cancellation_policy = fields.Html(
        related='company_id.tour_default_cancellation_policy',
        readonly=False,
        string='Default Cancellation Policy'
    )

