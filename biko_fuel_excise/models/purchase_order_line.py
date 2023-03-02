# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    biko_density_fact = fields.Float(string="Density")
    biko_density_15c = fields.Float(string="Density at 15 C")
    biko_product_qty_15c = fields.Float(string="Quantity at 15 C")

    def _prepare_stock_moves(self, picking):
        """Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ["product", "consu"]:
            return res

        price_unit = self._get_stock_move_price_unit()
        qty, qty_15c = self._get_qty_procurement()

        move_dests = self.move_dest_ids
        if not move_dests:
            move_dests = self.move_ids.move_dest_ids.filtered(
                lambda m: m.state != "cancel"
                and not m.location_dest_id.usage == "supplier"
            )

        if not move_dests:
            qty_to_attach = 0
            qty_to_attach_15c = 0
            qty_to_push = self.product_qty - qty
            qty_to_push_15c = self.biko_product_qty_15c - qty_15c
        else:
            move_dests_initial_demand = self.product_id.uom_id._compute_quantity(
                sum(
                    move_dests.filtered(
                        lambda m: m.state != "cancel"
                        and not m.location_dest_id.usage == "supplier"
                    ).mapped("product_qty")
                ),
                self.product_uom,
                rounding_method="HALF-UP",
            )
            qty_to_attach = move_dests_initial_demand - qty
            qty_to_push = self.product_qty - move_dests_initial_demand

            move_dests_initial_demand = sum(
                move_dests.filtered(
                    lambda m: m.state != "cancel"
                    and not m.location_dest_id.usage == "supplier"
                ).mapped("biko_product_qty_15c")
            )
            qty_to_attach_15c = move_dests_initial_demand - qty_15c
            qty_to_push_15c = self.biko_product_qty_15c - move_dests_initial_demand

        if (
            float_compare(
                qty_to_attach, 0.0, precision_rounding=self.product_uom.rounding
            )
            > 0
            or float_compare(
                qty_to_attach_15c, 0.0, precision_rounding=self.product_uom.rounding
            )
            > 0
        ):
            product_uom_qty, product_uom = self.product_uom._adjust_uom_quantities(
                qty_to_attach, self.product_id.uom_id
            )
            res.append(
                self._prepare_stock_move_vals(
                    picking, price_unit, product_uom_qty, product_uom, qty_to_attach_15c
                )
            )
        if not float_is_zero(
            qty_to_push, precision_rounding=self.product_uom.rounding
        ) or not float_is_zero(
            qty_to_push_15c, precision_rounding=self.product_uom.rounding
        ):
            product_uom_qty, product_uom = self.product_uom._adjust_uom_quantities(
                qty_to_push, self.product_id.uom_id
            )
            extra_move_vals = self._prepare_stock_move_vals(
                picking, price_unit, product_uom_qty, product_uom, qty_to_push_15c
            )
            extra_move_vals["move_dest_ids"] = False  # don't attach
            res.append(extra_move_vals)
        return res

    def _get_qty_procurement(self):
        self.ensure_one()
        qty = 0.0
        qty_15c = 0.0
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        for move in outgoing_moves:
            qty -= move.product_uom._compute_quantity(
                move.product_uom_qty, self.product_uom, rounding_method="HALF-UP"
            )
            qty_15c -= move.biko_product_qty_15c
        for move in incoming_moves:
            qty += move.product_uom._compute_quantity(
                move.product_uom_qty, self.product_uom, rounding_method="HALF-UP"
            )
            qty_15c += move.biko_product_qty_15c
        return (qty, qty_15c)

    def _prepare_stock_move_vals(
        self, picking, price_unit, product_uom_qty, product_uom, biko_product_qty_15c=0
    ):
        self.ensure_one()
        res = super(PurchaseOrderLine, self)._prepare_stock_move_vals(
            picking, price_unit, product_uom_qty, product_uom
        )
        res.update(
            {
                "biko_density_fact": self.biko_density_fact,
                "biko_density_15c": self.biko_density_15c,
                "biko_product_qty_15c": biko_product_qty_15c,
            }
        )

        return res

    def write(self, values):
        lines = self.filtered(lambda l: l.order_id.state == "purchase")
        result = super(PurchaseOrderLine, self).write(values)
        if "biko_product_qty_15c" in values:
            lines._create_or_update_picking()
        return result
