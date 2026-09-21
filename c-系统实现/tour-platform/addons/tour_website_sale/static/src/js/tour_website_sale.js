/* TMS Website Sale - 线路班期 + 人数预估合计（只读，最终价服务端重算） */
odoo.define('tour_website_sale.product_booking', function (require) {
    'use strict';

    var publicWidget = require('web.public.widget');

    publicWidget.registry.TourBookingPrice = publicWidget.Widget.extend({
        selector: '#tour_booking_wrap',

        start: function () {
            this.$select = this.$('#tour_departure_select');
            this.$counts = this.$('.tour_count');
            this.$total = this.$('#tour_total_preview');
            this.$select.on('change', this._refresh.bind(this));
            this.$counts.on('input', this._refresh.bind(this));
            this._refresh();
        },

        _refresh: function () {
            var opt = this.$select.find('option:selected');
            var prices = null;
            try {
                prices = JSON.parse(opt.data('prices') || 'null');
            } catch (e) {
                prices = null;
            }
            if (!prices) {
                this.$total.text('—');
                return;
            }
            var keys = ['adult', 'child', 'old_man', 'student', 'baby'];
            var total = 0.0;
            this.$counts.each(function (i, el) {
                var n = parseInt(el.value || '0', 10) || 0;
                total += n * (prices[keys[i]] || 0.0);
            });
            this.$total.text('¥' + total.toFixed(2));
        },
    });
});
