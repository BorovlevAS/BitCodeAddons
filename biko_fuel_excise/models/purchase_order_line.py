# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    biko_density_fact = fields.Float(string="Density", digits=(6, 4))
    biko_qty_kg = fields.Float(
        string="Quantity, kg",
        digits="Product Unit of Measure",
    )
    biko_price_kg = fields.Float(string="Price, kg", digits="Product Price")

    biko_density_15c = fields.Float(string="Density at 15 C", digits=(6, 4))
    biko_product_qty_15c = fields.Float(
        string="Quantity at 15 C",
        digits="Product Unit of Measure",
    )

    biko_lot_id = fields.Many2one("stock.production.lot", "Lot", copy=False)

    # Form view methods
    @api.onchange("biko_qty_kg")
    def _onchange_calculate_density(self):
        for rec in self:
            if rec.product_qty:
                rec.biko_density_fact = rec.biko_qty_kg / rec.product_qty
            else:
                rec.biko_density_fact = 0.0

    @api.onchange("product_qty", "biko_density_fact")
    def _onchange_calculate_qty_kg(self):
        for rec in self:
            rec.biko_qty_kg = rec.product_qty * rec.biko_density_fact
            if rec.biko_density_15c:
                rec.biko_product_qty_15c = rec.biko_qty_kg / rec.biko_density_15c
            else:
                rec.biko_product_qty_15c = 0.0

    @api.onchange("biko_density_15c")
    def _onchange_calculate_qty_15c(self):
        for rec in self:
            if rec.biko_density_15c:
                rec.biko_product_qty_15c = rec.biko_qty_kg / rec.biko_density_15c
            else:
                rec.biko_product_qty_15c = 0.0

    # Stock methods
    def _get_qty_15c_procurement(self):
        self.ensure_one()
        qty_15c = 0.0
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        for move in outgoing_moves:
            qty_15c -= move.product_uom._compute_quantity(
                move.biko_product_qty_15c, self.product_uom, rounding_method="HALF-UP"
            )
        for move in incoming_moves:
            qty_15c += move.product_uom._compute_quantity(
                move.biko_product_qty_15c, self.product_uom, rounding_method="HALF-UP"
            )
        return qty_15c

    def _prepare_stock_moves(self, picking):
        """Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ["product", "consu"]:
            return res

        price_unit = self._get_stock_move_price_unit()
        qty = self._get_qty_procurement()
        qty_15c = self._get_qty_15c_procurement()

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
            product_uom_qty_15c, product_uom = self.product_uom._adjust_uom_quantities(
                qty_to_push_15c, self.product_id.uom_id
            )
            extra_move_vals = self._prepare_stock_move_vals(
                picking, price_unit, product_uom_qty, product_uom, product_uom_qty_15c
            )
            extra_move_vals["move_dest_ids"] = False  # don't attach
            res.append(extra_move_vals)
        return res

    def _prepare_stock_move_vals(
        self, picking, price_unit, product_uom_qty, product_uom, biko_product_qty_15c=0
    ):
        self.ensure_one()
        res = super(PurchaseOrderLine, self)._prepare_stock_move_vals(
            picking, price_unit, product_uom_qty, product_uom
        )

        if not self.biko_lot_id:
            # search for existing lot
            # in stock.production.lot
            # search fields: product_id, biko_density_15
            res_lots = self.env["stock.production.lot"].search(
                [
                    ("product_id", "=", self.product_id.id),
                    ("biko_density_15c", "=", self.biko_density_15c),
                ],
                limit=1,
            )

            if res_lots:
                lot_id = res_lots[0]
            else:
                # create lot with biko_density_15
                lot_id = self.env["stock.production.lot"].create(
                    {
                        "product_id": self.product_id.id,
                        "biko_density_15c": self.biko_density_15c,
                        "company_id": self.company_id.id,
                        "name": str(self.biko_density_15c),
                    }
                )
        else:
            lot_id = self.biko_lot_id

        self.biko_lot_id = lot_id

        res.update(
            {
                "biko_density_fact": self.biko_density_fact,
                "biko_density_15c": self.biko_density_15c,
                "biko_product_qty_15c": biko_product_qty_15c,
                "restrict_lot_id": self.biko_lot_id.id,
                "biko_kg_qty_15c": self.biko_qty_kg,
            }
        )

        return res

    def _prepare_account_move_line(self, move=False):
        self.ensure_one()
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move=move)

        # if not self.biko_lot_id:
        #     lot_ids = self.env["stock.production.lot"].search(
        #         [
        #             ("product_id", "=", self.product_id.id),
        #             ("biko_density_15c", "=", self.biko_density_15c),
        #         ],
        #         limit=1,
        #     )

        #     if not lot_ids:
        #         # need to create lot
        #         lot_vals = {
        #             "company_id": self.company_id.id,
        #             "product_id": self.product_id.id,
        #             "name": self.biko_density_15c,
        #             "biko_density_15c": self.biko_density_15c,
        #         }
        #         lot_id = self.env["stock.production.lot"].create(lot_vals)
        #     else:
        #         lot_id = lot_ids[0]

        #     self.biko_lot_id = lot_id

        res.update(
            {
                "biko_density_fact": self.biko_density_fact,
                "biko_density_15c": self.biko_density_15c,
                "biko_product_qty_15c": self.biko_product_qty_15c,
                # "lot_id": self.biko_lot_id.id,
            }
        )
        return res

    # Global object's methods
    def write(self, values):
        lines = self.filtered(lambda l: l.order_id.state == "purchase")
        result = super(PurchaseOrderLine, self).write(values)
        if "biko_product_qty_15c" in values:
            lines._create_or_update_picking()
        return result
