from collections import defaultdict

from odoo import _, api, models, fields
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    biko_density_fact = fields.Float(string="Density", default=0.0, copy=False)
    biko_density_15c = fields.Float(string="Density at 15 C", default=0.0, copy=False)
    biko_product_qty_15c = fields.Float(
        string="Quantity at 15 C", default=0.0, copy=False
    )
    biko_product_qty_15c_done = fields.Float(
        string="Quantity at 15C Done",
        compute="_quantity_15c_done_compute",
        digits="Product Unit of Measure",
        inverse="_quantity_15c_done_set",
        store=True,
        compute_sudo=True,
    )

    @api.depends(
        "move_line_ids.biko_product_qty_15c_done",
        "move_line_nosuggest_ids.biko_product_qty_15c_done",
        "picking_type_id.show_reserved",
    )
    def _quantity_15c_done_compute(self):
        """This field represents the sum of the move lines `qty_done`. It allows the user to know
        if there is still work to do.

        We take care of rounding this value at the general decimal precision and not the rounding
        of the move's UOM to make sure this value is really close to the real sum, because this
        field will be used in `_action_done` in order to know if the move will need a backorder or
        an extra move.
        """
        if not any(self._ids):
            # onchange
            for move in self:
                quantity_15c_done = 0
                for move_line in move._get_move_lines():
                    quantity_15c_done += move_line.quantity_15c_done
                move.biko_product_qty_15c_done = quantity_15c_done
        else:
            # compute
            move_lines_ids = set()
            for move in self:
                move_lines_ids |= set(move._get_move_lines().ids)

            data = self.env["stock.move.line"].read_group(
                [("id", "in", list(move_lines_ids))],
                ["move_id", "biko_product_qty_15c_done"],
                ["move_id"],
                lazy=False,
            )

            rec = defaultdict(list)
            for d in data:
                rec[d["move_id"][0]] += [(d["biko_product_qty_15c_done"])]

            for move in self:
                move.biko_product_qty_15c_done = sum(
                    biko_product_qty_15c_done
                    for biko_product_qty_15c_done in rec.get(
                        move.ids[0] if move.ids else move.id, []
                    )
                )

    def _quantity_15c_done_set(self):
        quantity_15c_done = self[
            0
        ].biko_product_qty_15c_done  # any call to create will invalidate `move.quantity_done`
        for move in self:
            move_lines = move._get_move_lines()
            if not move_lines:
                if quantity_15c_done:
                    # do not impact reservation here
                    move_line = self.env["stock.move.line"].create(
                        dict(
                            move._prepare_move_line_vals(),
                            biko_product_qty_15c_done=quantity_15c_done,
                        )
                    )
                    move.write({"move_line_ids": [(4, move_line.id)]})
                    move_line._apply_putaway_strategy()
            elif len(move_lines) == 1:
                move_lines[0].biko_product_qty_15c_done = quantity_15c_done
            else:
                move._multi_line_quantity_done_set(quantity_15c_done)

    def _multi_line_quantity_15c_done_set(self, quantity_15c_done):
        move_lines = self._get_move_lines()
        # Bypass the error if we're trying to write the same value.
        ml_quantity_done = 0
        for move_line in move_lines:
            ml_quantity_done += move_line.biko_product_qty_15c_done
        if quantity_15c_done != ml_quantity_done:
            raise UserError(
                _(
                    "Cannot set the done quantity from this stock move, work directly with the move lines."
                )
            )

    def _prepare_move_line_vals(
        self, quantity=None, reserved_quant=None, biko_product_qty_15c=None
    ):
        self.ensure_one()

        vals = super(StockMove, self)._prepare_move_line_vals(quantity, reserved_quant)

        vals = {
            "move_id": self.id,
            "product_id": self.product_id.id,
            "product_uom_id": self.product_uom.id,
            "location_id": self.location_id.id,
            "location_dest_id": self.location_dest_id.id,
            "picking_id": self.picking_id.id,
            "company_id": self.company_id.id,
        }
        if biko_product_qty_15c:
            vals = dict(vals, biko_product_qty_15c=biko_product_qty_15c)

        return vals

    def _merge_moves_fields(self):
        """This method will return a dict of stock move’s values that represent the values of all moves in `self` merged."""
        res = super(StockMove, self)._merge_moves_fields()
        res.update({"biko_product_qty_15c": sum(self.mapped("biko_product_qty_15c"))})

        return res
