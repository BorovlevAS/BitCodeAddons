# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class ReportStock15CMoves(models.Model):
    _name = "report.stock15c.moves"
    _auto = False
    _description = "Stock Moves Report for 15C"

    date_start = fields.Date(string="Date Start", readonly=True)
    date_end = fields.Date(string="Date End", readonly=True)
    product_tmpl_id = fields.Many2one("product.template", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)

    product_qty = fields.Float(string="Quantity", readonly=True)
    move_ids = fields.One2many("stock.move", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", readonly=True)

    def init(self):

        tools.drop_view_if_exists(self._cr, "report_stock15c_moves")
        query = """
CREATE or REPLACE VIEW report_stock_quantity AS (
WITH
    existing_sm (id, product_id, tmpl_id, product_qty, date, state, company_id, whs_id, whd_id) AS (
        SELECT m.id, m.product_id, pt.id, m.product_qty, m.date, m.state, m.company_id, whs.id, whd.id
        FROM stock_move m
        LEFT JOIN stock_location ls on (ls.id=m.location_id)
        LEFT JOIN stock_location ld on (ld.id=m.location_dest_id)
        LEFT JOIN stock_warehouse whs ON ls.parent_path like concat('%/', whs.view_location_id, '/%')
        LEFT JOIN stock_warehouse whd ON ld.parent_path like concat('%/', whd.view_location_id, '/%')
        LEFT JOIN product_product pp on pp.id=m.product_id
        LEFT JOIN product_template pt on pt.id=pp.product_tmpl_id
        WHERE pt.type = 'product' AND
            (whs.id IS NOT NULL OR whd.id IS NOT NULL) AND
            (whs.id IS NULL OR whd.id IS NULL OR whs.id != whd.id) AND
            m.product_qty != 0 AND
            m.state NOT IN ('draft', 'cancel') AND
            (m.state != 'done' or m.date >= ((now() at time zone 'utc')::date - interval '3month'))
    ),
    all_sm (id, product_id, tmpl_id, product_qty, date, state, company_id, whs_id, whd_id) AS (
        SELECT sm.id, sm.product_id, sm.tmpl_id,
            CASE 
                WHEN is_duplicated = 0 THEN sm.product_qty
                WHEN sm.whs_id IS NOT NULL AND sm.whd_id IS NOT NULL AND sm.whs_id != sm.whd_id THEN sm.product_qty
                ELSE 0
            END, 
            sm.date, sm.state, sm.company_id,
            CASE WHEN is_duplicated = 0 THEN sm.whs_id END,
            CASE 
                WHEN is_duplicated = 0 AND NOT (sm.whs_id IS NOT NULL AND sm.whd_id IS NOT NULL AND sm.whs_id != sm.whd_id) THEN sm.whd_id 
                WHEN is_duplicated = 1 AND (sm.whs_id IS NOT NULL AND sm.whd_id IS NOT NULL AND sm.whs_id != sm.whd_id) THEN sm.whd_id 
            END
        FROM
            GENERATE_SERIES(0, 1, 1) is_duplicated,
            existing_sm sm
    )
SELECT
    MIN(id) as id,
    product_id,
    product_tmpl_id,
    state,
    date,
    sum(product_qty) as product_qty,
    company_id,
    warehouse_id
FROM (SELECT
        m.id,
        m.product_id,
        m.tmpl_id as product_tmpl_id,
        CASE
            WHEN m.whs_id IS NOT NULL AND m.whd_id IS NULL THEN 'out'
            WHEN m.whd_id IS NOT NULL AND m.whs_id IS NULL THEN 'in'
        END AS state,
        m.date::date AS date,
        CASE
            WHEN m.whs_id IS NOT NULL AND m.whd_id IS NULL THEN -m.product_qty
            WHEN m.whd_id IS NOT NULL AND m.whs_id IS NULL THEN m.product_qty
        END AS product_qty,
        m.company_id,
        CASE
            WHEN m.whs_id IS NOT NULL AND m.whd_id IS NULL THEN m.whs_id
            WHEN m.whd_id IS NOT NULL AND m.whs_id IS NULL THEN m.whd_id
        END AS warehouse_id
    FROM
        all_sm m
    WHERE
        m.product_qty != 0 AND
        m.state != 'done'
    UNION ALL
    SELECT
        -q.id as id,
        q.product_id,
        pp.product_tmpl_id,
        'forecast' as state,
        date.*::date,
        q.quantity as product_qty,
        q.company_id,
        wh.id as warehouse_id
    FROM
        GENERATE_SERIES((now() at time zone 'utc')::date - interval '3month',
        (now() at time zone 'utc')::date + interval '3 month', '1 day'::interval) date,
        stock_quant q
    LEFT JOIN stock_location l on (l.id=q.location_id)
    LEFT JOIN stock_warehouse wh ON l.parent_path like concat('%/', wh.view_location_id, '/%')
    LEFT JOIN product_product pp on pp.id=q.product_id
    WHERE
        (l.usage = 'internal' AND wh.id IS NOT NULL) OR
        l.usage = 'transit'
    UNION ALL
    SELECT
        m.id,
        m.product_id,
        m.tmpl_id as product_tmpl_id,
        'forecast' as state,
        GENERATE_SERIES(
        CASE
            WHEN m.state = 'done' THEN (now() at time zone 'utc')::date - interval '3month'
            ELSE m.date::date
        END,
        CASE
            WHEN m.state != 'done' THEN (now() at time zone 'utc')::date + interval '3 month'
            ELSE m.date::date - interval '1 day'
        END, '1 day'::interval)::date date,
        CASE
            WHEN m.whs_id IS NOT NULL AND m.whd_id IS NULL AND m.state = 'done' THEN m.product_qty
            WHEN m.whd_id IS NOT NULL AND m.whs_id IS NULL AND m.state = 'done' THEN -m.product_qty
            WHEN m.whs_id IS NOT NULL AND m.whd_id IS NULL THEN -m.product_qty
            WHEN m.whd_id IS NOT NULL AND m.whs_id IS NULL THEN m.product_qty
        END AS product_qty,
        m.company_id,
        CASE
            WHEN m.whs_id IS NOT NULL AND m.whd_id IS NULL THEN m.whs_id
            WHEN m.whd_id IS NOT NULL AND m.whs_id IS NULL THEN m.whd_id
        END AS warehouse_id
    FROM
        all_sm m
    WHERE
        m.product_qty != 0) AS forecast_qty
GROUP BY product_id, product_tmpl_id, state, date, company_id, warehouse_id
);
"""
        self.env.cr.execute(query)
