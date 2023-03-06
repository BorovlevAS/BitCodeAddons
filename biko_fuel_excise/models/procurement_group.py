import logging
from collections import defaultdict, namedtuple

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, fields, models, registry
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import float_compare, float_is_zero, html_escape
from odoo.tools.misc import split_every

_logger = logging.getLogger(__name__)


class ProcurementException(Exception):
    def __init__(self, procurement_exceptions):
        self.procurement_exceptions = procurement_exceptions


class ProcurementGroup(models.Model):
    _inherit = "procurement.group"

    @api.model
    def run(self, procurements, raise_user_error=True):
        def raise_exception(procurement_errors):
            if raise_user_error:
                dummy, errors = zip(*procurement_errors)
                raise UserError("\n".join(errors))
            else:
                raise ProcurementException(procurement_errors)

        actions_to_run = defaultdict(list)
        procurement_errors = []
        for procurement in procurements:
            procurement.values.setdefault(
                "company_id", procurement.location_id.company_id
            )
            procurement.values.setdefault("priority", "0")
            procurement.values.setdefault("date_planned", fields.Datetime.now())
            if procurement.product_id.type not in ("consu", "product") or (
                float_is_zero(
                    procurement.product_qty,
                    precision_rounding=procurement.product_uom.rounding,
                )
                and float_is_zero(
                    procurement.values.get("biko_product_qty_15c", 0.0),
                    precision_rounding=procurement.product_uom.rounding,
                )
            ):
                continue
            rule = self._get_rule(
                procurement.product_id, procurement.location_id, procurement.values
            )
            if not rule:
                error = _(
                    'No rule has been found to replenish "%s" in "%s".\nVerify the routes configuration on the product.'
                ) % (
                    procurement.product_id.display_name,
                    procurement.location_id.display_name,
                )
                procurement_errors.append((procurement, error))
            else:
                action = "pull" if rule.action == "pull_push" else rule.action
                actions_to_run[action].append((procurement, rule))

        if procurement_errors:
            raise_exception(procurement_errors)

        for action, procurements in actions_to_run.items():
            if hasattr(self.env["stock.rule"], "_run_%s" % action):
                try:
                    getattr(self.env["stock.rule"], "_run_%s" % action)(procurements)
                except ProcurementException as e:
                    procurement_errors += e.procurement_exceptions
            else:
                _logger.error(
                    "The method _run_%s doesn't exist on the procurement rules" % action
                )

        if procurement_errors:
            raise_exception(procurement_errors)
        return True
