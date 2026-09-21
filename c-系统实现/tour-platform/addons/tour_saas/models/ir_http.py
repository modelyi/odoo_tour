import logging

import werkzeug.exceptions

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

# The switch. A parameter and NOT an installation: cutting the service off and
# giving it back has to be instant and reversible, and this module ships inside
# the template, so the code is in every database from the moment it is born.
# Uninstalling a module can fail halfway through; writing a parameter cannot.
PARAM_SUSPENDED = "saas.suspended"

CLOSED_ROUTE = "/service-closed"

# What keeps working while the service is cut off.
#
# The back office does NOT hang off this (it is not frontend, so it never
# reaches `_frontend_pre_dispatch`), but some things served through the
# frontend do, and they would either break the closure page or lock the
# customer out: the static assets, the login, and the notice itself.
ALLOWED_PREFIXES = (
    CLOSED_ROUTE,
    "/web/login",
    "/web/session",
    "/web/reset_password",
    "/web/assets",
    "/web/image",
    "/web/content",
    "/website/translations",
    "/favicon.ico",
)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _frontend_pre_dispatch(cls):
        """Send the visitor to the closure notice when the service is cut off.

        It hooks into `_frontend_pre_dispatch` and not `_pre_dispatch` because
        that one runs for the frontend ONLY: the back office never passes
        through here, so the customer can still log in and fix their payment
        without anyone maintaining a list of backend routes to exclude.

        `abort(redirect)` is Odoo's own pattern for redirecting from a dispatch
        hook (see `http_routing/models/ir_http.py`).
        """
        super()._frontend_pre_dispatch()

        path = request.httprequest.path or "/"
        if path.startswith(ALLOWED_PREFIXES):
            # The closure page itself is in that list: without it the redirect
            # redirects to itself. `_frontend_pre_dispatch` also runs while
            # handling an error, so the loop would not be theoretical.
            return

        params = request.env["ir.config_parameter"].sudo()
        if params.get_param(PARAM_SUSPENDED) not in ("True", "true", "1"):
            return

        werkzeug.exceptions.abort(request.redirect(CLOSED_ROUTE, code=302))
