import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

PARAM_USERS = "saas.limit_users"
PARAM_PLAN = "saas.plan_name"
PARAM_BILLING = "saas.billing_url"


class ResUsers(models.Model):
    """The plan's user limit, enforced inside the customer's own database.

    **Count the result, not the intent.** `share` is a COMPUTED field: it is
    True when the user has no `base.group_user`. Reading it from the values
    handed to `create` tells you nothing, because it is almost never there ---
    and the first attempt at this did exactly that, counting every new user as
    an internal one. With a limit of two, the third customer who signed up on
    the website would have been unable to register: a limit meant for the
    customer's team blocking their own buyers.

    So Odoo is allowed to create or write, the result is counted, and the error
    is raised only if the limit was passed --- which rolls the whole operation
    back.
    """

    _inherit = "res.users"

    @api.model
    def _saas_limit(self):
        """How many internal users the plan includes. 0 = no limit."""
        value = self.env["ir.config_parameter"].sudo().get_param(PARAM_USERS)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @api.model
    def _saas_internal_users(self):
        """The ones that take up a seat in the plan.

        Portal users are left out: they are the customer's customers, and
        counting them would turn a team limit into a sales limit.
        """
        return self.sudo().search_count([
            ("share", "=", False), ("active", "=", True),
        ])

    @api.model_create_multi
    def create(self, vals_list):
        before = self._saas_internal_users()
        users = super().create(vals_list)
        self._saas_check_growth(before)
        return users

    def write(self, vals):
        # Only look when the write CAN add internal users. A name change
        # cannot, and that is what keeps user editing working even when the
        # limit is already exceeded --- which is exactly what happens right
        # after moving down a plan.
        watch = "active" in vals or "group_ids" in vals or "all_group_ids" in vals
        before = self._saas_internal_users() if watch else None
        result = super().write(vals)
        if watch:
            self._saas_check_growth(before)
        return result

    @api.model
    def _saas_check_growth(self, before):
        """Roll the operation back if it added internal users past the limit.

        **Only if it GREW.** Without that condition, moving down a plan with
        the team already in place would lock the database: any write on any
        user would fail, including deactivating someone to get back under the
        limit. The limit has to stop growth, not trap.
        """
        limit = self._saas_limit()
        if not limit or before is None:
            return
        now = self._saas_internal_users()
        if now <= before or now <= limit:
            return
        params = self.env["ir.config_parameter"].sudo()
        plan = params.get_param(PARAM_PLAN)
        url = params.get_param(PARAM_BILLING)
        message = _(
            "Your plan%(plan)s includes %(limit)s user(s) and you already have "
            "%(count)s.",
            plan=" (%s)" % plan if plan else "", limit=limit, count=before,
        )
        if url:
            # A limit with no way out is a wall; with the way out it is an offer.
            message += _("\n\nYou can change your plan here: %s", url)
        raise ValidationError(message)
