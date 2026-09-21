import logging

_logger = logging.getLogger(__name__)

# The parameters the central instance writes INSIDE this database, and what
# they were called before this module existed. A module that is sold cannot
# read keys carrying another author's prefix, so they were renamed --- and
# databases that were already running still have the old ones.
RENAMED = {
    "puntofy.tienda_apagada": "saas.suspended",
    "puntofy.limite_usuarios": "saas.limit_users",
    "puntofy.limite_productos": "saas.limit_products",
    # Branches are added by Puntofy's private layer and were NOT here: found on
    # 2026-09-15 while sweeping the public identifiers. A limit that does not
    # travel stops blocking instead of blocking too much, which is exactly the
    # failure mode this hook exists to prevent.
    "puntofy.limite_sucursales": "saas.limit_branches",
    "puntofy.nombre_del_plan": "saas.plan_name",
    "puntofy.url_facturacion": "saas.billing_url",
}


def post_init_hook(env):
    """Carry what the central instance had already written to the new keys.

    THE FIRST ONE IS THE ONE THAT MATTERS, and you do not see it coming:
    `puntofy.tienda_apagada` is the switch. A database SUSPENDED for non-payment
    has it set to True; this module reads `saas.suspended`, which is born empty.
    So installing this would **give the service back to someone who did not
    pay**, with nothing saying so.

    The limits are the same problem inverted: `0` means "no limit", so a
    database that was not migrated stops blocking anything instead of blocking
    too much.

    And the old key IS DELETED. The first version copied and left both, and
    that is not caution: it is two copies of the same truth, with the central
    instance updating only one. The limit being enforced ends up being the
    PREVIOUS plan's, frozen, and nothing says so --- which is the failure that
    turned up on 2026-09-15 on the reader's side.

    The delete happens after the new key is written, never before: if something
    blows up in between, what is left is the duplicated value (harmless) rather
    than no value at all (which, on `saas.suspended`, would mean giving the
    service back to someone who did not pay).
    """
    P = env["ir.config_parameter"].sudo()
    moved = []
    for old, new in RENAMED.items():
        value = P.get_param(old)
        if value in (False, None, ""):
            continue
        P.set_param(new, value)
        P.set_param(old, False)
        moved.append("%s=%r" % (new, value))
    if moved:
        _logger.warning(
            "tour_saas: moved %d parameter(s) off their old names: "
            "%s", len(moved), ", ".join(moved))
