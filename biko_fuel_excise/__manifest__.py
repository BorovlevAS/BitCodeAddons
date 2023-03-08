# -*- coding: utf-8 -*-
{
    "name": "BIKO: Модуль добавляет логику работы с ",
    "version": "15.0.1.1.5",
    "author": "Borovlev A.S.",
    "company": "BIKO Solutions",
    "depends": [
        "sale",
        "purchase",
        "stock",
        "sale_stock",
    ],
    "data": [
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_move_views.xml",
        "views/account_move_views.xml",
        "reports/report_stock15c_moves_views.xml",
        "wizards/stock_15c_moves_wizard_views.xml",
        "security/ir.model.access.csv",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False,
}
