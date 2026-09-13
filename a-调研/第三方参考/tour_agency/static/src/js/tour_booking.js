/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.TourBookingForm = publicWidget.Widget.extend({
    selector: '.js_tour_booking_form',
    events: {
        'change .js_num_passengers': '_onPassengerChange',
        'input .js_num_passengers': '_onPassengerChange',
    },

    start: function () {
        this._super.apply(this, arguments);
        // Get package data from form attributes for client-side calculation
        this.packageId = this.$el.data('package-id');
        this.priceType = this.$el.data('price-type');
        this.adultPrice = parseFloat(this.$el.data('adult-price')) || 0;
        this.childPrice = parseFloat(this.$el.data('child-price')) || 0;
        this.infantPrice = parseFloat(this.$el.data('infant-price')) || 0;
        this.currency = this.$el.data('currency') || '';
        
        // Update price immediately
        this._updatePrice();
    },

    _onPassengerChange: function () {
        this._updatePrice();
    },

    _getPassengerCounts: function () {
        return {
            adults: parseInt(this.$('#num_adults').val()) || 1,
            children: parseInt(this.$('#num_children').val()) || 0,
            infants: parseInt(this.$('#num_infants').val()) || 0,
        };
    },

    _formatPrice: function (price) {
        return this.currency + ' ' + price.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    },

    _calculateClientSidePrice: function () {
        const counts = this._getPassengerCounts();
        let total = 0;
        
        if (this.priceType === 'per_person') {
            total += counts.adults * this.adultPrice;
            total += counts.children * this.childPrice;
            total += counts.infants * this.infantPrice;
        } else {
            total = this.adultPrice; // For per_package, use the base price
        }
        
        return total;
    },

    async _updatePrice() {
        const counts = this._getPassengerCounts();
        
        // Show client-side calculated price immediately for responsiveness
        const clientSideTotal = this._calculateClientSidePrice();
        this.$('.js_total_price').text(this._formatPrice(clientSideTotal));

        // Also fetch from server to ensure accuracy
        try {
            const result = await rpc('/tour/calculate-price', {
                package_id: this.packageId,
                num_adults: counts.adults,
                num_children: counts.children,
                num_infants: counts.infants,
            });
            
            if (result.success) {
                this.$('.js_total_price').text(result.formatted_total);
                this.$('.js_total_price').data('currency-symbol', result.currency);
            } else if (result.error) {
                console.error('Price calculation error:', result.error);
            }
        } catch (error) {
            console.error('RPC error:', error);
            // Keep client-side calculated price as fallback
        }
    },
});

export default publicWidget.registry.TourBookingForm;

