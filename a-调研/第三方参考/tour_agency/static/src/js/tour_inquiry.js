/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.TourInquiryForm = publicWidget.Widget.extend({
    selector: '.js_tour_inquiry_form',
    events: {
        'submit': '_onFormSubmit',
    },

    _onFormSubmit: function (ev) {
        const packageId = this.$('#package_id').val();
        if (!packageId) {
            ev.preventDefault();
            alert('Please select a tour package');
            return false;
        }
        
        const email = this.$('#customer_email').val();
        if (email && !this._validateEmail(email)) {
            ev.preventDefault();
            alert('Please enter a valid email address');
            return false;
        }
        
        return true;
    },

    _validateEmail: function (email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },
});

export default publicWidget.registry.TourInquiryForm;

