# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.gmaps_service import GoogleMapsService


class CpqTransportWizard(models.TransientModel):
    _name = "cpq.transport.wizard"
    _description = "Transport Configuration Wizard"

    sale_line_id = fields.Many2one(
        "sale.order.line", required=True, ondelete="cascade"
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="sale_line_id.order_id.currency_id",
        readonly=True,
    )

    origin_address = fields.Char(string="Origin address")
    destination_address = fields.Char(string="Destination address")
    trip_type = fields.Selection(
        [("one_way", "One-way"), ("round_trip", "Round-trip")],
        string="Trip type",
        required=True,
        default="one_way",
    )
    price_per_km = fields.Monetary(
        string="Price / km",
        currency_field="currency_id",
    )

    one_way_km = fields.Float(
        string="One-way distance (km)",
        digits=(10, 2),
        readonly=True,
    )
    distance_km = fields.Float(
        string="Distance (km)",
        digits=(10, 2),
        compute="_compute_distance_km",
    )
    computed_price = fields.Monetary(
        string="Computed price",
        compute="_compute_computed_price",
        currency_field="currency_id",
    )
    last_signature = fields.Char(readonly=True)
    last_computed_at = fields.Datetime(readonly=True)

    state = fields.Selection(
        [("draft", "Draft"), ("computed", "Computed"), ("stale", "Needs recompute")],
        default="draft",
        readonly=True,
    )
    warning_msg = fields.Char(readonly=True)

    # ------------------------------------------------------------------
    @api.depends("one_way_km", "trip_type")
    def _compute_distance_km(self):
        for wiz in self:
            factor = 2.0 if wiz.trip_type == "round_trip" else 1.0
            wiz.distance_km = (wiz.one_way_km or 0.0) * factor

    @api.depends("distance_km", "price_per_km")
    def _compute_computed_price(self):
        for wiz in self:
            wiz.computed_price = (wiz.distance_km or 0.0) * (wiz.price_per_km or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            if rec.one_way_km and rec._current_signature() == (rec.last_signature or ""):
                rec.state = "computed"
        return recs

    def _current_signature(self):
        self.ensure_one()
        return "%s|%s" % (
            (self.origin_address or "").strip().lower(),
            (self.destination_address or "").strip().lower(),
        )

    @api.onchange("origin_address", "destination_address")
    def _onchange_addresses(self):
        for wiz in self:
            if wiz.one_way_km and wiz._current_signature() != (wiz.last_signature or ""):
                wiz.state = "stale"
                wiz.warning_msg = _("Addresses changed — please recompute the distance.")
            elif wiz.one_way_km:
                wiz.state = "computed"
                wiz.warning_msg = False
            else:
                wiz.state = "draft"
                wiz.warning_msg = False

    # ------------------------------------------------------------------
    def action_compute_distance(self):
        self.ensure_one()
        if not self.origin_address or not self.destination_address:
            raise UserError(_("Please fill in both origin and destination addresses."))
        ICP = self.env["ir.config_parameter"].sudo()
        api_key = ICP.get_param("cpq_transport.gmaps_api_key")
        if not api_key:
            raise UserError(_(
                "Google Routes API key is missing. Set it in "
                "Settings → Sales → Transport."
            ))

        distance_km, status, err_msg = GoogleMapsService.get_distance_km(
            self.origin_address, self.destination_address, api_key,
        )
        if status != "OK":
            raise UserError(self._humanize_status(status, err_msg))

        self.write({
            "one_way_km": distance_km,
            "state": "computed",
            "last_signature": self._current_signature(),
            "last_computed_at": fields.Datetime.now(),
            "warning_msg": False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "cpq.transport.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": {"dialog_size": "medium"},
        }

    def action_validate(self):
        self.ensure_one()
        if self.state != "computed":
            raise UserError(_("Please compute the distance first."))
        if self._current_signature() != (self.last_signature or ""):
            raise UserError(_("Addresses or trip type changed — please recompute the distance."))

        line = self.sale_line_id
        cfg = line.transport_config_id
        vals = {
            "sale_line_id": line.id,
            "origin_address": self.origin_address,
            "destination_address": self.destination_address,
            "trip_type": self.trip_type,
            "price_per_km": self.price_per_km,
            "one_way_km": self.one_way_km,
            "last_signature": self.last_signature,
            "last_computed_at": self.last_computed_at,
        }
        if cfg:
            cfg.write(vals)
        else:
            cfg = self.env["cpq.transport.config"].create(vals)
            line.transport_config_id = cfg.id

        # Update line — transport is a forfait, force qty=1 and update price_unit.
        line.write({
            "product_uom_qty": 1.0,
            "price_unit": cfg.computed_price,
            "name": cfg.summary or line.name,
        })
        return {"type": "ir.actions.act_window_close"}

    # ------------------------------------------------------------------
    @staticmethod
    def _humanize_status(status, err_msg):
        mapping = {
            "ZERO_RESULTS": _("No route found between the two addresses."),
            "OVER_QUERY_LIMIT": _("Google Routes quota exceeded. Try again later."),
            "REQUEST_DENIED": _("Google Routes refused the request (check your API key and enabled APIs)."),
            "INVALID_REQUEST": _("Invalid request sent to Google Routes."),
            "NETWORK_ERROR": _("Network error while contacting Google Routes: %s") % (err_msg or ""),
            "MISSING_KEY": _("Google Routes API key is not configured."),
        }
        return mapping.get(status, _("Google Routes error: %s") % (err_msg or status))
