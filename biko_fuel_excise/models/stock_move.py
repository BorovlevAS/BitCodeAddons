from collections import defaultdict

from odoo import _, api, exceptions, models, fields
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    biko_density_fact = fields.Float(string="Density", digits=(6, 4), default=0.0)
    biko_density_15c = fields.Float(
        string="Density at 15 C", digits=(6, 4), default=0.0
    )
    biko_product_qty_15c = fields.Float(string="Quantity at 15 C", default=0.0)

    biko_kg_qty_15c = fields.Float(
        string="Qty in Kg"
    )  # Количество топлива в кг. Фактическое. Ошибка в названии поля

    biko_product_qty_15c_done = fields.Float(
        string="Quantity at 15C Done",
        compute="_quantity_15c_done_compute",
        digits="Product Unit of Measure",
        inverse="_quantity_15c_done_set",
        store=True,
        compute_sudo=True,
    )

    is_quantity_15c_done_editable = fields.Boolean(
        "Is quantity 15C done editable",
        compute="_compute_is_quantity_15c_done_editable",
    )

    restrict_lot_id = fields.Many2one(
        "stock.production.lot", string="Restrict Lot", copy=False
    )

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super(StockMove, self)._prepare_merge_moves_distinct_fields()
        distinct_fields.append("restrict_lot_id")
        return distinct_fields

    @api.depends("state", "picking_id", "product_id")
    def _compute_is_quantity_15c_done_editable(self):
        for move in self:
            if not move.product_id:
                move.is_quantity_15c_done_editable = False
            elif (
                not move.picking_id.immediate_transfer
                and move.picking_id.state == "draft"
            ):
                move.is_quantity_15c_done_editable = False
            elif move.picking_id.is_locked and move.state in ("done", "cancel"):
                move.is_quantity_15c_done_editable = False
            elif move.show_details_visible:
                move.is_quantity_15c_done_editable = False
            elif move.show_operations:
                move.is_quantity_15c_done_editable = False
            else:
                move.is_quantity_15c_done_editable = True

    @api.depends(
        "move_line_ids.biko_product_qty_15c_done",
        "move_line_nosuggest_ids.biko_product_qty_15c_done",
        "picking_type_id.show_reserved",
    )
    def _quantity_15c_done_compute(self):

        if not any(self._ids):
            # onchange
            for move in self:
                quantity_15c_done = 0
                for move_line in move._get_move_lines():
                    quantity_15c_done += move_line.biko_product_qty_15c_done
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
        # any call to create will invalidate `move.quantity_done`
        quantity_15c_done = self[0].biko_product_qty_15c_done
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

        # vals.update({"biko_kg_qty_15c": self.biko_kg_qty_15c})
        if biko_product_qty_15c:
            vals = dict(vals, biko_product_qty_15c=biko_product_qty_15c)
        else:
            vals = dict(vals, biko_product_qty_15c=self.biko_product_qty_15c)

        if self.restrict_lot_id:
            if (
                "lot_id" in vals
                and vals["lot_id"] is not False
                and vals["lot_id"] != self.restrict_lot_id.id
            ):
                raise exceptions.UserError(
                    _(
                        "Inconsistencies between reserved quant and lot restriction on "
                        "stock move"
                    )
                )
            vals["lot_id"] = self.restrict_lot_id.id

        return vals

    def _merge_moves_fields(self):
        """This method will return a dict of stock move’s values that represent the values of all moves in `self` merged."""
        res = super(StockMove, self)._merge_moves_fields()
        res.update({"biko_product_qty_15c": sum(self.mapped("biko_product_qty_15c"))})

        return res

    def _prepare_procurement_values(self):
        proc_values = super()._prepare_procurement_values()
        proc_values.update(
            {
                "biko_density_fact": self.biko_density_fact,
                "biko_density_15c": self.biko_density_15c,
                "biko_product_qty_15c": self.biko_product_qty_15c,
                "biko_kg_qty_15c": self.biko_kg_qty_15c,
                "restrict_lot_id": self.restrict_lot_id.id,
            }
        )
        return proc_values

    def _set_quantities_to_reservation(self):
        super(StockMove, self)._set_quantities_to_reservation()

        for move in self:
            if move.state not in ("partially_available", "assigned"):
                continue
            for move_line in move.move_line_ids:
                if move.has_tracking != "none" and not (
                    move_line.lot_id or move_line.lot_name
                ):
                    continue
                move_line.biko_product_qty_15c_done = move_line.biko_product_qty_15c

    def _get_available_quantity(
        self,
        location_id,
        lot_id=None,
        package_id=None,
        owner_id=None,
        strict=False,
        allow_negative=False,
    ):
        self.ensure_one()
        if not lot_id and self.restrict_lot_id:
            lot_id = self.restrict_lot_id
        return super()._get_available_quantity(
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
            allow_negative=allow_negative,
        )

    def _update_reserved_quantity(
        self,
        need,
        available_quantity,
        location_id,
        lot_id=None,
        package_id=None,
        owner_id=None,
        strict=True,
    ):
        self.ensure_one()
        if self.restrict_lot_id:
            lot_id = self.restrict_lot_id
        return super()._update_reserved_quantity(
            need,
            available_quantity,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
        )

    def _split(self, qty, restrict_partner_id=False):
        vals_list = super()._split(qty, restrict_partner_id=restrict_partner_id)
        if vals_list and self.restrict_lot_id:
            vals_list[0]["restrict_lot_id"] = self.restrict_lot_id.id
        return vals_list
