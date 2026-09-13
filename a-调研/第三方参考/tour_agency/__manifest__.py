# -*- coding: utf-8 -*-
{
    'name': 'Tours and Travel Management System - All in one (with Portal)',
    'version': '18.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Complete Tours and Travel Management System with Website Booking, CRM, Sales & Portal',
    'description': """
        Tours and Travel Management System
        ===================================
        
        Odoo Website Tour Agency simplifies travel business management with integrated CRM, website booking, 
        calendar scheduling, contacts, live chat, employee management, purchases, invoicing, and sales.
        
        Key Features:
        * Create & showcase engaging tour packages with images, descriptions, and pricing
        * Enable online tour booking and secure payment integration
        * Manage itineraries, travel schedules, and availability with ease
        * Handle customer inquiries and automate email responses
        * Mobile-friendly design for a smooth user experience
        * Integration with Odoo CRM, Accounting, and Sales for end-to-end travel business management
        * Customer portal for viewing bookings and tour details
        * Hotel and accommodation management
        * Transportation management
        * Meal planning
        * Attraction and activity management
        * Multi-currency and multi-language support
        
        Manage tour operations, automate bookings, and enhance customer experiences—all in one powerful solution!
    """,
    'author': 'Cyshield',
    'website': 'https://www.cyshield.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'website',
        'portal',
        'crm',
        'sale_management',
        'account',
        'calendar',
        'contacts',
        'mail',
        'hr',
        'purchase',
        'payment',
        'website_payment',
        'website_sale',
    ],
    'data': [
        # Security
        'security/tour_agency_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/tour_package_data.xml',
        'data/email_template_data.xml',
        'data/website_menu_data.xml',
        
        # Views - Backend
        'views/tour_package_views.xml',
        'views/tour_inquiry_views.xml',
        'views/tour_booking_views.xml',
        'views/tour_itinerary_views.xml',
        'views/tour_hotel_views.xml',
        'views/tour_transportation_views.xml',
        'views/tour_meal_views.xml',
        'views/tour_attraction_views.xml',
        'views/tour_expense_views.xml',
        'views/tour_configuration_views.xml',
        'views/tour_menu_views.xml',
        'views/inherited_views.xml',
        
        # Views - Website
        'views/website_homepage.xml',
        'views/website_tour_templates.xml',
        'views/website_tour_package_list.xml',
        'views/website_tour_package_detail.xml',
        'views/website_tour_booking.xml',
        'views/website_tour_inquiry.xml',
        'views/website_tour_snippets.xml',
        
        # Views - Portal
        'views/portal_tour_templates.xml',
        
        # Wizards
        'wizard/tour_booking_wizard_views.xml',
        
        # Reports
        'report/tour_booking_report.xml',
        'report/tour_itinerary_report.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'tour_agency/static/src/css/tour_website.css',
            'tour_agency/static/src/js/tour_booking.js',
            'tour_agency/static/src/js/tour_inquiry.js',
        ],
        'web.assets_backend': [
            'tour_agency/static/src/css/tour_backend.css',
        ],
    },
    'demo': [
        'data/tour_demo_data.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': [
        'static/description/screenshots/ss_1.png',
        'static/description/cyshield.png',
        'static/description/icon.png',
        'static/description/screenshots/ss_2.png',
        'static/description/screenshots/ss_3.png',
        'static/description/screenshots/ss_4.png',
        'static/description/screenshots/ss_5.png',
        'static/description/screenshots/ss_6.png',
        'static/description/screenshots/ss_7.png',
        'static/description/screenshots/ss_8.png',
        'static/description/screenshots/ss_9.png',
        'static/description/screenshots/ss_10.png',
        'static/description/screenshots/ss_11.png',
        'static/description/screenshots/ss_12.png',
        'static/description/screenshots/ss_13.png',
        'static/description/screenshots/ss_14.png',
        'static/description/screenshots/ss_15.png',
        'static/description/screenshots/ss_16.png',
        'static/description/screenshots/ss_17.png',
    ],
}

