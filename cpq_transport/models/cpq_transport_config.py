# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CpqTransportConfig(models.Model):
    _name = "cpq.transport.config"
    _description = "Transport Configuration (per quotation line)"

    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Quotation Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    origin_address = fields.Char(string="Origin address", required=True)
    destination_address = fields.Char(string="Destination address", required=True)
    trip_type = fields.Selection(
        [("one_way", "One-way"), ("round_trip", "Round-trip")],
        string="Trip type",
        required=True,
        default="one_way",
    )
    price_per_km = fields.Monetary(
        string="Price / km",
        required=True,
        currency_field="currency_id",
    )
    one_way_km = fields.Float(
        string="One-way distance (km)",
        digits=(10, 2),
        readonly=True,
        help="Raw one-way distance returned by the routing API. "
             "The displayed distance_km is doubled when trip_type is round_trip.",
    )
    distance_km = fields.Float(
        string="Distance (km)",
        digits=(10, 2),
        compute="_compute_distance_km",
        store=True,
    )
    computed_price = fields.Monetary(
        string="Computed price",
        compute="_compute_computed_price",
        store=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="sale_line_id.order_id.currency_id",
        store=True,
        readonly=True,
    )
    last_computed_at = fields.Datetime(string="Last computed at", readonly=True)
    last_signature = fields.Char(
        string="Last computed signature",
        readonly=True,
        help="Hash of (origin, destination, trip_type) at last successful compute.",
    )
    is_stale = fields.Boolean(
        string="Needs recompute",
        compute="_compute_is_stale",
    )
    summary = fields.Char(
        string="Summary",
        compute="_compute_summary",
        store=True,
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends("one_way_km", "trip_type")
    def _compute_distance_km(self):
        for rec in self:
            factor = 2.0 if rec.trip_type == "round_trip" else 1.0
            rec.distance_km = (rec.one_way_km or 0.0) * factor

    @api.depends("distance_km", "price_per_km")
    def _compute_computed_price(self):
        for rec in self:
            rec.computed_price = (rec.distance_km or 0.0) * (rec.price_per_km or 0.0)

    @api.depends(
        "origin_address",
        "destination_address",
        "trip_type",
        "last_signature",
        "one_way_km",
    )
    def _compute_is_stale(self):
        for rec in self:
            if not rec.one_way_km:
                rec.is_stale = True
                continue
            rec.is_stale = rec._signature() != (rec.last_signature or "")

    @api.depends(
        "origin_address",
        "destination_address",
        "trip_type",
        "distance_km",
        "price_per_km",
        "currency_id",
    )
    def _compute_summary(self):
        for rec in self:
            if not rec.distance_km:
                rec.summary = False
                continue
            trip_label = _("Round-trip") if rec.trip_type == "round_trip" else _("One-way")
            symbol = rec.currency_id.symbol or ""
            rec.summary = "%s → %s · %s · %.2f km · %.2f %s/km" % (
                rec.origin_address or "",
                rec.destination_address or "",
                trip_label,
                rec.distance_km,
                rec.price_per_km or 0.0,
                symbol,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _signature(self):
        """Signature over addresses only.

        trip_type is NOT part of the signature because switching one-way ↔
        round-trip does not require a new API call — it only changes the
        multiplier applied to the one-way distance.
        """
        self.ensure_one()
        return "%s|%s" % (
            (self.origin_address or "").strip().lower(),
            (self.destination_address or "").strip().lower(),
        )
