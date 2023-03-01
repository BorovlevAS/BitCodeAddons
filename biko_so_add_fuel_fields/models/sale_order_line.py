# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    biko_density_fact = fields.Float(string="Density")
    biko_density_15c = fields.Float(string="Density at 15 C")
    biko_product_qty_15c = fields.Float(string="Quantity at 15 C")
