# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class TourExpense(models.Model):
    _name = 'tour.expense'
    _description = 'Tour Expense'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    
    name = fields.Char(string='Description', required=True, tracking=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.today, tracking=True)
    expense_date = fields.Date(string='Expense Date', default=fields.Date.today,
                                help='Date when the expense occurred')
    description = fields.Text(string='Detailed Description')
    
    # Package/Booking Reference (at least one required)
    package_id = fields.Many2one('tour.package', string='Package', 
                                  ondelete='cascade', index=True,
                                  help='Link expense to a package (for general package expenses)')
    booking_id = fields.Many2one('tour.booking', string='Booking', 
                                  ondelete='cascade', index=True,
                                  help='Link expense to a specific booking (for trip-specific expenses)')
    
    # Expense Details
    expense_type = fields.Selection([
        ('hotel', 'Hotel'),
        ('transportation', 'Transportation'),
        ('meal', 'Meal'),
        ('attraction', 'Attraction/Entry Fee'),
        ('guide', 'Guide Fee'),
        ('tip', 'Tip/Gratuity'),
        ('marketing', 'Marketing'),
        ('emergency', 'Emergency'),
        ('other', 'Other'),
    ], string='Type', required=True, default='other', tracking=True)
    
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                   default=lambda self: self.env.company.currency_id, required=True)
    
    # Payment
    paid_by = fields.Many2one('res.users', string='Paid By', default=lambda self: self.env.user)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('online', 'Online Payment'),
        ('other', 'Other'),
    ], string='Payment Method', default='cash')
    
    # Reference
    reference = fields.Char(string='Reference')
    invoice_reference = fields.Char(string='Invoice Reference')
    
    # Attachment
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # Company
    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True)
    
    def action_approve(self):
        self.write({'state': 'approved'})
    
    def action_reject(self):
        self.write({'state': 'rejected'})

