# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CpqTransportProduct(models.Model):
    _name = "cpq.transport.product"
    _description = "Configurable Transport Service"
    _order = "name"

    name = fields.Char(string="Name", required=True)
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Odoo Product",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Internal notes")

    default_price_per_km = fields.Monetary(
        string="Default price / km",
        currency_field="currency_id",
        help="Pre-fills the price per km when a user opens the transport "
             "configurator on a quotation line. The user can still override it.",
    )
    origin_default = fields.Char(
        string="Default origin",
        help="Pre-fills the origin address (e.g. company warehouse address). "
             "Optional.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="product_tmpl_id.currency_id",
        readonly=True,
    )

    _product_tmpl_uniq = models.Constraint(
        "UNIQUE(product_tmpl_id)",
        "A product template can only be linked to one Transport service.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Force type=service on the linked product template
        recs = super().create(vals_list)
        for rec in recs:
            if rec.product_tmpl_id and rec.product_tmpl_id.type != "service":
                rec.product_tmpl_id.type = "service"
        return recs
