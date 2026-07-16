# -*- coding: utf-8 -*-
{
    "name": "Google Maps Delivery Pricing — Distance Quote & Address Autocomplete",
    "version": "19.0.1.0.3",
    "summary": "Add delivery, shipping or transport products to quotations. Google Maps address autocomplete and automatic road-distance pricing per kilometer.",
    "description": """
Google Maps Delivery Pricing for Odoo Sales
============================================
Automatic delivery pricing for Odoo Sales, powered by Google Maps.

Add any shipping, transport or courier product to a quotation, enter
the destination address (Google Places autocomplete), and the road
distance is computed via Google Maps Routes API. The line price is
updated automatically based on the per-kilometer rate.

Perfect for
-----------
* Moving companies & relocation services
* Freight & logistics — regional or long-distance shipments
* E-commerce fulfillment with distance-based delivery fees
* Waste removal & skip hire — trip pricing to customer site
* Field service — travel time / mileage billing
* Courier services — same-day, express, refrigerated delivery
* Any business billing delivery per kilometer

Features
--------
* Google Maps address autocomplete on origin & destination fields
* Real road distance via Google Maps Routes API (not straight-line)
* One-way and round-trip pricing
* Zero-click auto-computation after address selection
* Unlimited transport / delivery services with their own rates
* Native Sales quotation integration (smart button + line summary)
* Full configuration history for audit
""",
    "author": "Expodo",
    "website": "https://expodo.fr",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "depends": ["sale_management", "product"],
    "data": [
        "security/ir.model.access.csv",
        "views/cpq_transport_product_views.xml",
        "views/cpq_transport_config_views.xml",
        "views/menu.xml",
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/cpq_transport_wizard_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "assets": {
        "web.assets_backend": [
            "cpq_transport/static/src/js/transport_places_v2.js",
            "cpq_transport/static/src/xml/transport_places_v2.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
