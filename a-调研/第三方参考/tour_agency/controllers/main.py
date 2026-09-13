# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from odoo.addons.website.controllers.main import QueryURL
import json


class WebsiteTourAgency(http.Controller):
    
    @http.route(['/tours', '/tours/page/<int:page>'], type='http', auth='public', website=True, sitemap=True)
    def tour_packages(self, page=1, category=None, tag=None, search='', **kwargs):
        """Display tour packages listing"""
        
        domain = [('state', '=', 'published'), ('is_published', '=', True)]
        
        # Apply filters
        if category:
            domain.append(('category_id', '=', int(category)))
        if tag:
            domain.append(('tag_ids', 'in', [int(tag)]))
        if search:
            domain += ['|', ('name', 'ilike', search), ('destination', 'ilike', search)]
        
        # Sorting
        sort_order = kwargs.get('sort', 'sequence')
        if sort_order == 'name':
            order = 'name asc'
        elif sort_order == 'price_low':
            order = 'base_price asc'
        elif sort_order == 'price_high':
            order = 'base_price desc'
        elif sort_order == 'popular':
            order = 'booking_count desc, view_count desc'
        else:
            order = 'sequence, name'
        
        # Pagination
        packages_per_page = 12
        total_packages = request.env['tour.package'].search_count(domain)
        
        pager = request.website.pager(
            url='/tours',
            total=total_packages,
            page=page,
            step=packages_per_page,
            url_args={'category': category, 'tag': tag, 'search': search, 'sort': sort_order}
        )
        
        packages = request.env['tour.package'].search(
            domain, 
            limit=packages_per_page, 
            offset=pager['offset'],
            order=order
        )
        
        # Get categories and tags for filters
        categories = request.env['tour.package.category'].search([('active', '=', True)])
        tags = request.env['tour.package.tag'].search([('active', '=', True)])
        
        # Featured packages
        featured_packages = request.env['tour.package'].search([
            ('state', '=', 'published'),
            ('is_published', '=', True),
            ('is_featured', '=', True)
        ], limit=6)
        
        values = {
            'packages': packages,
            'pager': pager,
            'categories': categories,
            'tags': tags,
            'featured_packages': featured_packages,
            'search': search,
            'current_category': int(category) if category else None,
            'current_tag': int(tag) if tag else None,
            'current_sort': sort_order,
            'keep': QueryURL('/tours', category=category, tag=tag, search=search),
        }
        
        return request.render('tour_agency.tour_packages_page', values)
    
    @http.route(['/tour/package/<model("tour.package"):package>'], type='http', auth='public', website=True, sitemap=True)
    def tour_package_detail(self, package, **kwargs):
        """Display tour package details"""
        
        # Increment view count
        package.increment_view_count()
        
        # Get related packages (same category)
        related_packages = request.env['tour.package'].search([
            ('id', '!=', package.id),
            ('category_id', '=', package.category_id.id),
            ('state', '=', 'published'),
            ('is_published', '=', True)
        ], limit=4)
        
        values = {
            'package': package,
            'related_packages': related_packages,
            'main_object': package,
        }
        
        return request.render('tour_agency.tour_package_detail_page', values)
    
    @http.route(['/tour/inquiry'], type='http', auth='public', website=True, sitemap=False)
    def tour_inquiry_page(self, **kwargs):
        """Display inquiry form page"""
        packages = request.env['tour.package'].search([
            ('state', '=', 'published'),
            ('is_published', '=', True)
        ], order='name')
        
        values = {
            'packages': packages,
            'package_id': kwargs.get('package_id'),
        }
        
        return request.render('tour_agency.tour_inquiry_page', values)
    
    @http.route(['/tour/inquiry/submit'], type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def tour_inquiry_submit(self, **post):
        """Submit inquiry form"""
        
        try:
            # Get package
            package_id = int(post.get('package_id'))
            package = request.env['tour.package'].browse(package_id)
            
            if not package.exists():
                return request.render('website.404')
            
            # Create inquiry
            inquiry_vals = {
                'package_id': package_id,
                'customer_name': post.get('customer_name'),
                'customer_email': post.get('customer_email'),
                'customer_phone': post.get('customer_phone'),
                'customer_mobile': post.get('customer_mobile'),
                'preferred_date': post.get('preferred_date') if post.get('preferred_date') else False,
                'num_adults': int(post.get('num_adults', 1)),
                'num_children': int(post.get('num_children', 0)),
                'num_infants': int(post.get('num_infants', 0)),
                'subject': post.get('subject', ''),
                'message': post.get('message'),
                'special_requirements': post.get('special_requirements', ''),
                'source': 'website',
            }
            
            # Link to logged-in user's partner if available
            if not request.env.user._is_public():
                inquiry_vals['partner_id'] = request.env.user.partner_id.id
            
            inquiry = request.env['tour.inquiry'].sudo().create(inquiry_vals)
            
            return request.render('tour_agency.tour_inquiry_success', {
                'inquiry': inquiry,
                'package': package,
            })
            
        except Exception as e:
            return request.render('tour_agency.tour_inquiry_error', {
                'error': str(e)
            })
    
    @http.route(['/tour/booking/<model("tour.package"):package>'], type='http', auth='user', website=True)
    def tour_booking_page(self, package, **kwargs):
        """Display booking form page"""
        
        partner = request.env.user.partner_id
        
        values = {
            'package': package,
            'partner': partner,
            'num_adults': int(kwargs.get('num_adults', 1)),
            'num_children': int(kwargs.get('num_children', 0)),
            'num_infants': int(kwargs.get('num_infants', 0)),
            'travel_date': kwargs.get('travel_date', ''),
        }
        
        return request.render('tour_agency.tour_booking_page', values)
    
    @http.route(['/tour/booking/submit'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def tour_booking_submit(self, **post):
        """Submit booking form"""
        
        try:
            # Get package
            package_id = int(post.get('package_id'))
            package = request.env['tour.package'].browse(package_id)
            
            if not package.exists():
                return request.render('website.404')
            
            partner = request.env.user.partner_id
            
            # Create booking
            booking_vals = {
                'package_id': package_id,
                'partner_id': partner.id,
                'travel_start_date': post.get('travel_start_date'),
                'num_adults': int(post.get('num_adults', 1)),
                'num_children': int(post.get('num_children', 0)),
                'num_infants': int(post.get('num_infants', 0)),
                'customer_notes': post.get('customer_notes', ''),
                'special_requirements': post.get('special_requirements', ''),
                'source': 'website',
                'state': 'draft',
            }
            
            booking = request.env['tour.booking'].sudo().create(booking_vals)
            
            # Redirect to payment or confirmation
            return request.redirect(f'/my/bookings/{booking.id}?access_token={booking._portal_ensure_token()}')
            
        except Exception as e:
            return request.render('tour_agency.tour_booking_error', {
                'error': str(e),
                'package': package,
            })
    
    @http.route(['/tour/booking/<int:booking_id>/confirm'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def tour_booking_confirm(self, booking_id, **post):
        """Confirm booking"""
        
        booking = request.env['tour.booking'].browse(booking_id)
        
        if not booking.exists() or booking.partner_id != request.env.user.partner_id:
            return request.render('website.404')
        
        if booking.state == 'draft':
            booking.sudo().action_confirm()
        
        return request.redirect(f'/my/bookings/{booking.id}?message=confirmed')
    
    @http.route(['/tour/booking/<int:booking_id>/cancel'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def tour_booking_cancel(self, booking_id, **post):
        """Cancel booking from website"""
        
        booking = request.env['tour.booking'].browse(booking_id)
        
        if not booking.exists() or booking.partner_id != request.env.user.partner_id:
            return request.render('website.404')
        
        if booking.state in ['draft', 'confirmed']:
            booking.sudo().action_cancel()
        
        return request.redirect(f'/my/bookings/{booking.id}?message=cancelled')
    
    @http.route(['/tour/booking/<int:booking_id>/pay'], type='http', auth='user', website=True)
    def tour_booking_pay(self, booking_id, **post):
        """Redirect to payment for booking"""
        
        booking = request.env['tour.booking'].browse(booking_id)
        
        if not booking.exists() or booking.partner_id != request.env.user.partner_id:
            return request.render('website.404')
        
        # If booking has a sale order, redirect to its payment
        if booking.sale_order_id:
            return request.redirect(booking.sale_order_id.get_portal_url())
        
        # Otherwise show the booking payment page
        return request.render('tour_agency.tour_booking_payment', {
            'booking': booking,
        })
    
    @http.route(['/tour/search/autocomplete'], type='json', auth='public', website=True)
    def tour_search_autocomplete(self, term='', **kwargs):
        """Autocomplete for tour search"""
        
        if not term or len(term) < 2:
            return []
        
        packages = request.env['tour.package'].search([
            ('state', '=', 'published'),
            ('is_published', '=', True),
            '|', ('name', 'ilike', term), ('destination', 'ilike', term)
        ], limit=10)
        
        results = []
        for package in packages:
            results.append({
                'id': package.id,
                'name': package.name,
                'destination': package.destination,
                'price': package.base_price,
                'currency': package.currency_id.symbol,
                'url': f'/tour/package/{package.id}',
                'image': f'/web/image/tour.package/{package.id}/image_512',
            })
        
        return results
    
    @http.route(['/tour/category/<model("tour.package.category"):category>'], type='http', auth='public', website=True)
    def tour_category(self, category, **kwargs):
        """Display packages by category"""
        return self.tour_packages(category=category.id, **kwargs)
    
    @http.route(['/tour/destination/<string:destination>'], type='http', auth='public', website=True)
    def tour_by_destination(self, destination, page=1, **kwargs):
        """Display packages by destination"""
        
        domain = [
            ('state', '=', 'published'),
            ('is_published', '=', True),
            ('destination', 'ilike', destination)
        ]
        
        packages_per_page = 12
        total_packages = request.env['tour.package'].search_count(domain)
        
        pager = request.website.pager(
            url=f'/tour/destination/{destination}',
            total=total_packages,
            page=page,
            step=packages_per_page,
        )
        
        packages = request.env['tour.package'].search(
            domain,
            limit=packages_per_page,
            offset=pager['offset'],
            order='sequence, name'
        )
        
        values = {
            'packages': packages,
            'pager': pager,
            'destination': destination,
        }
        
        return request.render('tour_agency.tour_packages_by_destination', values)
    
    @http.route(['/tour/calculate-price'], type='json', auth='public', website=True)
    def calculate_tour_price(self, package_id, num_adults=1, num_children=0, num_infants=0, **kwargs):
        """Calculate tour price based on passengers"""
        
        package = request.env['tour.package'].browse(int(package_id))
        
        if not package.exists():
            return {'error': 'Package not found'}
        
        total = 0
        if package.price_type == 'per_person':
            total += num_adults * (package.adult_price or package.base_price)
            total += num_children * (package.child_price or 0)
            total += num_infants * (package.infant_price or 0)
        else:
            total = package.base_price
        
        return {
            'success': True,
            'total': total,
            'currency': package.currency_id.symbol,
            'formatted_total': f"{package.currency_id.symbol} {total:,.2f}",
        }

