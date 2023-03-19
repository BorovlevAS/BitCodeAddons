# добавить в модель stock.production.lot поле biko_density_15c. тип float
from odoo import fields, models


class StockProductionLot(models.Model):
    _inherit = "stock.production.lot"

    biko_density_15c = fields.Float(string="Density 15c")
