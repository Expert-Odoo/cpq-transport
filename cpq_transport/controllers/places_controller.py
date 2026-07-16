# -*- coding: utf-8 -*-
"""HTTP controllers for cpq_transport (Places autocomplete proxy)."""
from odoo import http
from odoo.http import request

from ..models.gmaps_service import GooglePlacesService


class CpqTransportPlacesController(http.Controller):

    @http.route(
        "/cpq_transport/autocomplete",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def autocomplete(self, query=None, language=None, **kwargs):
        """JSON-RPC endpoint used by the transport_autocomplete OWL widget.

        Returns a list of suggestions of the form
        [{"text": "10 rue de la Paix, Paris, France", "place_id": "ChIJ..."}].

        Never exposes the raw API key to the browser.
        """
        if not query or len(query.strip()) < 3:
            return {"suggestions": [], "status": "OK"}

        api_key = request.env["ir.config_parameter"].sudo().get_param(
            "cpq_transport.gmaps_api_key"
        )
        lang = (language or request.env.user.lang or "fr").split("_")[0]
        suggestions, status, err = GooglePlacesService.autocomplete(
            query, api_key, language=lang,
        )
        return {
            "suggestions": suggestions,
            "status": status,
            "error": err,
        }
