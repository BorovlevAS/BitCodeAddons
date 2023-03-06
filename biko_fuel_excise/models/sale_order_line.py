# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.float_utils import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    biko_density_fact = fields.Float(string="Density")
    biko_density_15c = fields.Float(string="Density at 15 C")
    biko_product_qty_15c = fields.Float(string="Quantity at 15 C")
    biko_kg_qty_15c = fields.Float(string="Qty in Kg")

    biko_qty_15c_deliv = fields.Float(
        compute="_compute_biko_qty_15c_deliv",
        string="15 C Delivered",
        store=True,
    )

    biko_qty_15c_to_invoice = fields.Float(
        compute="_get_to_invoice_qty_15c",
        string="15 C To Inv",
        store=True,
        digits="Product Unit of Measure",
    )

    biko_qty_15c_invoiced = fields.Float(
        compute="_compute_qty_15c_invoiced",
        string="15 C Invoiced",
        store=True,
        digits="Product Unit of Measure",
    )

    @api.depends(
        "invoice_lines.move_id.state",
        "invoice_lines.biko_product_qty_15c",
        "untaxed_amount_to_invoice",
    )
    def _compute_qty_15c_invoiced(self):

        for line in self:
            qty_invoiced = 0.0
            for invoice_line in line._get_invoice_lines():
                if (
                    invoice_line.move_id.state != "cancel"
                    or invoice_line.move_id.payment_state == "invoicing_legacy"
                ):
                    if invoice_line.move_id.move_type == "out_invoice":
                        qty_invoiced += invoice_line.product_uom_id._compute_quantity(
                            invoice_line.biko_product_qty_15c, line.product_uom
                        )
                    elif invoice_line.move_id.move_type == "out_refund":
                        qty_invoiced -= invoice_line.product_uom_id._compute_quantity(
                            invoice_line.biko_product_qty_15c, line.product_uom
                        )
            line.biko_qty_15c_invoiced = qty_invoiced

    @api.depends(
        "biko_qty_15c_invoiced",
        "biko_qty_15c_deliv",
        "product_uom_qty",
        "order_id.state",
    )
    def _get_to_invoice_qty_15c(self):

        for line in self:
            if line.order_id.state in ["sale", "done"]:
                if line.product_id.invoice_policy == "order":
                    line.biko_qty_15c_to_invoice = (
                        line.biko_product_qty_15c - line.biko_qty_15c_invoiced
                    )
                else:
                    line.biko_qty_15c_to_invoice = (
                        line.biko_qty_15c_deliv - line.biko_qty_15c_invoiced
                    )
            else:
                line.biko_qty_15c_to_invoice = 0

    @api.depends(
        "move_ids.state",
        "move_ids.scrapped",
        "move_ids.product_uom_qty",
        "move_ids.product_uom",
        "move_ids.biko_product_qty_15c",
    )
    def _compute_biko_qty_15c_deliv(self):

        for line in self:
            if line.qty_delivered_method == "stock_move":
                qty = 0.0
                outgoing_moves, incoming_moves = line._get_outgoing_incoming_moves()
                for move in outgoing_moves:
                    if move.state != "done":
                        continue
                    qty += move.product_uom._compute_quantity(
                        move.biko_product_qty_15c,
                        line.product_uom,
                        rounding_method="HALF-UP",
                    )
                for move in incoming_moves:
                    if move.state != "done":
                        continue
                    qty -= move.product_uom._compute_quantity(
                        move.biko_product_qty_15c,
                        line.product_uom,
                        rounding_method="HALF-UP",
                    )
                line.biko_qty_15c_deliv = qty

    def _prepare_procurement_values(self, group_id=False):
        """Prepare specific key for moves or other components that will be created from a stock rule
        comming from a sale order line. This method could be override in order to add other custom key that could
        be used in move/po creation.
        """
        values = super(SaleOrderLine, self)._prepare_procurement_values(group_id)
        self.ensure_one()
        # Use the delivery date if there is else use date_order and lead time
        values.update(
            {
                "biko_density_fact": self.biko_density_fact,
                "biko_density_15c": self.biko_density_15c,
                "biko_product_qty_15c": self.biko_product_qty_15c,
                "biko_kg_qty_15c": self.biko_kg_qty_15c,
            }
        )
        return values

    def _get_qty_procurement(
        self, previous_product_uom_qty=False, field_name="product_uom_qty"
    ):
        self.ensure_one()
        qty = 0.0
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        for move in outgoing_moves:
            qty += move.product_uom._compute_quantity(
                move[field_name], self.product_uom, rounding_method="HALF-UP"
            )
        for move in incoming_moves:
            qty -= move.product_uom._compute_quantity(
                move[field_name], self.product_uom, rounding_method="HALF-UP"
            )
        return qty

    def _action_launch_stock_rule(
        self, previous_product_uom_qty=False, previos_qty_15=False
    ):
        """
        Тут пришлось переделать запуск правил, чтобы передавать значение
        количества топлива в 15 градусов.
        лучшего способа не нашел, поэтому переопределил метод
        """

        if self._context.get("skip_procurement"):
            return True
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        procurements = []
        for line in self:
            line = line.with_company(line.company_id)
            if line.state != "sale" or not line.product_id.type in ("consu", "product"):
                continue
            qty = line._get_qty_procurement(previous_product_uom_qty)
            qty_15c = line._get_qty_procurement(
                previos_qty_15, field_name="biko_product_qty_15c"
            )
            # стандартно метод проеряет количнство товара на изменение.
            # т.к. у нас теперь два поля, то добавил проверку на изменение второго поля
            if (
                float_compare(qty, line.product_uom_qty, precision_digits=precision)
                == 0
            ) and (
                float_compare(
                    qty_15c, line.biko_product_qty_15c, precision_digits=precision
                )
                == 0
            ):
                continue

            group_id = line._get_procurement_group()
            if not group_id:
                group_id = self.env["procurement.group"].create(
                    line._prepare_procurement_group_vals()
                )
                line.order_id.procurement_group_id = group_id
            else:
                # In case the procurement group is already created and the order was
                # cancelled, we need to update certain values of the group.
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update(
                        {"partner_id": line.order_id.partner_shipping_id.id}
                    )
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({"move_type": line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

            values = line._prepare_procurement_values(group_id=group_id)
            values["biko_product_qty_15c"] = line.biko_product_qty_15c - qty_15c
            product_qty = line.product_uom_qty - qty

            line_uom = line.product_uom
            quant_uom = line.product_id.uom_id
            product_qty, procurement_uom = line_uom._adjust_uom_quantities(
                product_qty, quant_uom
            )
            procurements.append(
                self.env["procurement.group"].Procurement(
                    line.product_id,
                    product_qty,
                    procurement_uom,
                    line.order_id.partner_shipping_id.property_stock_customer,
                    line.product_id.display_name,
                    line.order_id.name,
                    line.order_id.company_id,
                    values,
                )
            )
        if procurements:
            self.env["procurement.group"].run(procurements)

        # This next block is currently needed only because the scheduler trigger is done by picking confirmation rather than stock.move confirmation
        orders = self.mapped("order_id")
        for order in orders:
            pickings_to_confirm = order.picking_ids.filtered(
                lambda p: p.state not in ["cancel", "done"]
            )
            if pickings_to_confirm:
                # Trigger the Scheduler for Pickings
                pickings_to_confirm.action_confirm()
        return True

    def write(self, values):
        lines = self.env["sale.order.line"]
        if "biko_product_qty_15c" in values:
            lines = self.filtered(lambda r: r.state == "sale" and not r.is_expense)

        previous_product_uom_qty_15 = {
            line.id: line.biko_product_qty_15c for line in lines
        }
        res = super(SaleOrderLine, self).write(values)
        if lines:
            lines._action_launch_stock_rule(
                previous_product_uom_qty=False,
                previos_qty_15=previous_product_uom_qty_15,
            )

        return res

    def _prepare_invoice_line(self, **optional_values):

        self.ensure_one()
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        res.update(
            {
                "biko_density_fact": self.biko_density_fact,
                "biko_density_15c": self.biko_density_15c,
                "biko_product_qty_15c": self.biko_qty_15c_to_invoice,
                "biko_kg_qty_15c": self.biko_kg_qty_15c,
            }
        )
        return res
