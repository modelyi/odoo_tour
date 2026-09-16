from odoo import http
from odoo.http import request


class ServiceClosed(http.Controller):

    @http.route("/service-closed", type="http", auth="public", website=True,
                sitemap=False, methods=["GET"])
    def service_closed(self, **_kwargs):
        """The notice the visitor sees.

        Returns **503**, not 200 and not 404: it is "not available right now",
        which is what it actually is. A 200 tells the search engine this is the
        site's page and gets it indexed; a 404 tells it the page is gone and
        gets it dropped. A 503 says come back later, and when the customer
        pays, their ranking is still where it was.
        """
        response = request.render("tour_saas.page_service_closed", {})
        response.status_code = 503
        # No intermediary may cache the closure: when the bill is paid, the
        # site has to come back at once.
        response.headers["Cache-Control"] = "no-store"
        response.headers["Retry-After"] = "86400"
        return response
