from odoo import _, api, models, fields


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    biko_density_fact = fields.Float(string="Density", default=0.0, copy=False)
    biko_density_15c = fields.Float(string="Density at 15 C", default=0.0, copy=False)
    biko_product_qty_15c = fields.Float(
        string="Quantity at 15 C", default=0.0, copy=False
    )
    biko_product_qty_15c_done = fields.Float(
        string="Quantity at 15 C Done", default=0.0, copy=False
    )
