# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    transport_gmaps_api_key = fields.Char(
        string="Google API key",
        config_parameter="cpq_transport.gmaps_api_key",
        help="Google Cloud API key used for both Routes API "
             "(distance computation) and Places API (address autocomplete).",
    )
