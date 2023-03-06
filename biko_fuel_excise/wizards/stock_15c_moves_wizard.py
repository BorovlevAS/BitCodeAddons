from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError


class Stock15CMovesWizard(models.TransientModel):
    _name = "stock.15c.moves.wizard"
    _description = "Stock 15C Moves Wizard"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.user.company_id.id,
    )
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")

    def check_date_range(self):
        if self.end_date < self.start_date:
            raise ValidationError(_("End Date should be greater than Start Date."))

    def fill_moves_data(self):
        self.env["stock.15c.moves.report"].sudo().search([]).unlink()
        sql = """
            with 
                locations as (
                    select id, complete_name as name
                    from stock_location
                    where stock_location.company_id=%s and stock_location.usage='internal'
                ),
                moves as (
                    select 
                        sml.product_id, 
                        sml.id as move_id,
                        sml.date,
                        sml.location_dest_id as location_id,
                        locations.name,
                        case when (location_dest_id=locations.id and sml.date < %s) then sml.biko_product_qty_15c_done else 0 end as qty_start,
                        case when (location_dest_id=locations.id and sml.date >=%s and sml.date <%s) then sml.biko_product_qty_15c_done else 0 end as qty_plus,
                        0 as qty_minus,
                        case when (location_dest_id=locations.id and sml.date <%s) then sml.biko_product_qty_15c_done else 0 end as qty_end
                    from locations
                    left join stock_move_line as sml on (sml.location_dest_id=locations.id)
                    UNION ALL
                    select 
                        sml.product_id, 
                        sml.move_id,
                        sml.date,
                        sml.location_id,
                        locations.name,
                        case when (location_id=locations.id  and sml.date <%s) then -sml.biko_product_qty_15c_done else 0 end,
                        0,
                        case when (location_id=locations.id and sml.date >=%s and sml.date <%s) then -sml.biko_product_qty_15c_done else 0 end,
                        case when (location_id=locations.id  and sml.date <%s) then -sml.biko_product_qty_15c_done else 0 end
                    from stock_move_line as sml
                    right join locations on (sml.location_id=locations.id)
                )

                select 
                    moves.product_id, 
                    moves.location_id, 
                    products.categ_id as category_id,
                    sum(moves.qty_start) as qty_start,
                    sum(moves.qty_plus) as qty_in,
                    sum(moves.qty_minus) as qty_out,
                    sum(moves.qty_end) as qty_end
                from moves
                left join (
                    select 
                        pp.id as prod_id, 
                        pt.categ_id as categ_id 
                    from product_product as pp
                    left join product_template as pt on (pp.product_tmpl_id=pt.id)
                ) as products on (moves.product_id = products.prod_id)
                where moves.product_id is not null
                group by (moves.product_id,moves.location_id,products.categ_id)

        """
        result = self.env.cr.execute(
            sql,
            (
                self.company_id.id,
                self.start_date,
                self.start_date,
                self.end_date,
                self.end_date,
                self.start_date,
                self.start_date,
                self.end_date,
                self.end_date,
            ),
        )

        data = self.env.cr.dictfetchall()

        for item in data:
            self.env["stock.15c.moves.report"].sudo().create(item)

    def open_report(self):
        self.check_date_range()
        self.fill_moves_data()

        action = {
            "name": "Stock 15C Moves",
            "type": "ir.actions.act_window",
            "view_mode": "pivot",
            "view_type": "pivot",
            "res_model": "stock.15c.moves.report",
            "view_id": self.env.ref("biko_fuel_excise.biko_stock15c_moves").id,
        }

        return action
