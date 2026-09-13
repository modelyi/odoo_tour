# -*- coding: utf-8 -*-

from collections import OrderedDict
from odoo import http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.tools import groupby as groupbyelem
from operator import itemgetter


class TourPortal(CustomerPortal):
    
    def _prepare_home_portal_values(self, counters):
        """Add tour bookings and inquiries to portal home"""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        if 'booking_count' in counters:
            values['booking_count'] = request.env['tour.booking'].search_count([
                ('partner_id', '=', partner.id)
            ]) if request.env['tour.booking'].check_access_rights('read', raise_exception=False) else 0
        
        if 'inquiry_count' in counters:
            values['inquiry_count'] = request.env['tour.inquiry'].search_count([
                ('partner_id', '=', partner.id)
            ]) if request.env['tour.inquiry'].check_access_rights('read', raise_exception=False) else 0
        
        return values
    
    # Tour Bookings
    @http.route(['/my/bookings', '/my/bookings/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_bookings(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        """Display customer bookings"""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        BookingObj = request.env['tour.booking']
        
        domain = [('partner_id', '=', partner.id)]
        
        searchbar_sortings = {
            'date': {'label': _('Booking Date'), 'order': 'booking_date desc'},
            'travel_date': {'label': _('Travel Date'), 'order': 'travel_start_date desc'},
            'name': {'label': _('Reference'), 'order': 'name'},
            'state': {'label': _('Status'), 'order': 'state'},
        }
        
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'draft': {'label': _('Draft'), 'domain': [('state', '=', 'draft')]},
            'confirmed': {'label': _('Confirmed'), 'domain': [('state', '=', 'confirmed')]},
            'in_progress': {'label': _('In Progress'), 'domain': [('state', '=', 'in_progress')]},
            'completed': {'label': _('Completed'), 'domain': [('state', '=', 'completed')]},
        }
        
        # Default sort and filter
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']
        
        # Date filter
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]
        
        # Count for pager
        booking_count = BookingObj.search_count(domain)
        
        # Pager
        pager = portal_pager(
            url='/my/bookings',
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'filterby': filterby},
            total=booking_count,
            page=page,
            step=self._items_per_page
        )
        
        # Get bookings
        bookings = BookingObj.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_bookings_history'] = bookings.ids[:100]
        
        values.update({
            'date': date_begin,
            'bookings': bookings,
            'page_name': 'booking',
            'pager': pager,
            'default_url': '/my/bookings',
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'sortby': sortby,
            'filterby': filterby,
        })
        
        return request.render('tour_agency.portal_my_bookings', values)
    
    @http.route(['/my/bookings/<int:booking_id>'], type='http', auth='user', website=True)
    def portal_my_booking_detail(self, booking_id, access_token=None, **kw):
        """Display booking details"""
        try:
            booking_sudo = self._document_check_access('tour.booking', booking_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        values = self._booking_get_page_view_values(booking_sudo, access_token, **kw)
        
        return request.render('tour_agency.portal_my_booking_detail', values)
    
    def _booking_get_page_view_values(self, booking, access_token, **kwargs):
        """Prepare values for booking detail page"""
        values = {
            'page_name': 'booking',
            'booking': booking,
            'message': kwargs.get('message', ''),
        }
        # Clean up history to remove deleted records before calling parent method
        history_list = request.session.get('my_bookings_history', [])
        if history_list:
            # Filter to only existing records
            existing_ids = request.env['tour.booking'].sudo().search([('id', 'in', history_list)]).ids
            request.session['my_bookings_history'] = [bid for bid in history_list if bid in existing_ids]
        
        return self._get_page_view_values(booking, access_token, values, 'my_bookings_history', False, **kwargs)
    
    @http.route(['/my/bookings/<int:booking_id>/cancel'], type='http', auth='user', website=True, methods=['POST'])
    def portal_my_booking_cancel(self, booking_id, **kw):
        """Cancel booking from portal"""
        try:
            booking_sudo = self._document_check_access('tour.booking', booking_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        if booking_sudo.state in ['draft', 'confirmed']:
            booking_sudo.action_cancel()
            return request.redirect(f'/my/bookings/{booking_id}?message=cancelled')
        
        return request.redirect(f'/my/bookings/{booking_id}')
    
    # Tour Inquiries
    @http.route(['/my/inquiries', '/my/inquiries/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_inquiries(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        """Display customer inquiries"""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        InquiryObj = request.env['tour.inquiry']
        
        domain = [('partner_id', '=', partner.id)]
        
        searchbar_sortings = {
            'date': {'label': _('Date'), 'order': 'inquiry_date desc'},
            'name': {'label': _('Reference'), 'order': 'name'},
            'state': {'label': _('Status'), 'order': 'state'},
        }
        
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'new': {'label': _('New'), 'domain': [('state', '=', 'new')]},
            'in_progress': {'label': _('In Progress'), 'domain': [('state', '=', 'in_progress')]},
            'quoted': {'label': _('Quoted'), 'domain': [('state', '=', 'quoted')]},
            'converted': {'label': _('Converted'), 'domain': [('state', '=', 'converted')]},
        }
        
        # Default sort and filter
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']
        
        # Count for pager
        inquiry_count = InquiryObj.search_count(domain)
        
        # Pager
        pager = portal_pager(
            url='/my/inquiries',
            url_args={'sortby': sortby, 'filterby': filterby},
            total=inquiry_count,
            page=page,
            step=self._items_per_page
        )
        
        # Get inquiries
        inquiries = InquiryObj.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        
        values.update({
            'inquiries': inquiries,
            'page_name': 'inquiry',
            'pager': pager,
            'default_url': '/my/inquiries',
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'sortby': sortby,
            'filterby': filterby,
        })
        
        return request.render('tour_agency.portal_my_inquiries', values)
    
    @http.route(['/my/inquiries/<int:inquiry_id>'], type='http', auth='user', website=True)
    def portal_my_inquiry_detail(self, inquiry_id, **kw):
        """Display inquiry details"""
        try:
            inquiry_sudo = self._document_check_access('tour.inquiry', inquiry_id)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        values = {
            'page_name': 'inquiry',
            'inquiry': inquiry_sudo,
        }
        
        return request.render('tour_agency.portal_my_inquiry_detail', values)

