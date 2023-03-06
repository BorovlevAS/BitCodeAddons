from copy import deepcopy

from odoo import models, api, _, fields


class ReportStock15CMoves(models.Model):
    _name = "stock.15c.moves.report"
    # _auto = False
    _description = "Report stock 15C moves"

    product_id = fields.Many2one("product.product", "Product", readonly=True)
    category_id = fields.Many2one("product.category", string="Category", readonly=True)
    location_id = fields.Many2one("stock.location", "Location", readonly=True)
    qty_start = fields.Float("Start Quantity", readonly=True)
    qty_end = fields.Float("End Quantity", readonly=True)
    qty_in = fields.Float("Quantity In", readonly=True)
    qty_out = fields.Float("Quantity Out", readonly=True)
