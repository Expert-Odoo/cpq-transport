# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    cpq_transport_product_id = fields.Many2one(
        "cpq.transport.product",
        string="Transport service",
        compute="_compute_cpq_transport_product_id",
        store=True,
    )
    is_transport = fields.Boolean(
        compute="_compute_cpq_transport_product_id",
        store=True,
    )
    transport_config_id = fields.Many2one(
        "cpq.transport.config",
        string="Transport configuration",
        ondelete="set null",
        copy=False,
    )
    transport_summary = fields.Char(
        related="transport_config_id.summary",
        store=True,
        string="Transport summary",
    )

    @api.depends("product_id")
    def _compute_cpq_transport_product_id(self):
        for line in self:
            if line.product_id:
                cpq = self.env["cpq.transport.product"].search(
                    [("product_tmpl_id", "=", line.product_id.product_tmpl_id.id)],
                    limit=1,
                )
                line.cpq_transport_product_id = cpq
                line.is_transport = bool(cpq)
            else:
                line.cpq_transport_product_id = False
                line.is_transport = False

    def _compute_display_name(self):
        """Show 'Product [× qty] ✓/○' in the transport selector."""
        if self.env.context.get("cpq_transport_selector"):
            for line in self:
                qty = "%.0f × " % line.product_uom_qty if line.product_uom_qty != 1 else ""
                status = " ✓" if line.transport_config_id else " ○"
                line.display_name = "%s%s%s" % (qty, line.product_id.name or "", status)
        else:
            super()._compute_display_name()

    def action_configure_transport(self):
        self.ensure_one()
        if not self.is_transport:
            return False
        if not self.id or not isinstance(self.id, int):
            raise UserError(_("Please save the quotation before configuring the transport."))

        cpq = self.cpq_transport_product_id
        default_price = cpq.default_price_per_km if cpq and cpq.default_price_per_km else 0.0
        default_origin = cpq.origin_default if cpq else False

        cfg = self.transport_config_id
        vals = {
            "sale_line_id": self.id,
            "origin_address": cfg.origin_address if cfg else default_origin,
            "destination_address": cfg.destination_address if cfg else False,
            "trip_type": cfg.trip_type if cfg else "one_way",
            "price_per_km": cfg.price_per_km if cfg else default_price,
            "one_way_km": cfg.one_way_km if cfg else 0.0,
            "last_signature": cfg.last_signature if cfg else False,
            "last_computed_at": cfg.last_computed_at if cfg else False,
        }
        wizard = self.env["cpq.transport.wizard"].create(vals)
        return {
            "type": "ir.actions.act_window",
            "name": _("Configure transport"),
            "res_model": "cpq.transport.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": {"dialog_size": "medium"},
        }


class SaleOrder(models.Model):
    _inherit = "sale.order"

    transport_line_count = fields.Integer(
        string="Transport lines",
        compute="_compute_transport_line_count",
    )
    transport_unconfigured_count = fields.Integer(
        string="Unconfigured transport lines",
        compute="_compute_transport_line_count",
    )

    @api.depends("order_line.is_transport", "order_line.transport_config_id")
    def _compute_transport_line_count(self):
        for order in self:
            tlines = order.order_line.filtered("is_transport")
            order.transport_line_count = len(tlines)
            order.transport_unconfigured_count = len(
                tlines.filtered(lambda l: not l.transport_config_id)
            )

    def action_configure_transport_lines(self):
        """Smart-button entry point.

        - 0 transport line → nothing
        - 1 transport line → open wizard directly
        - N transport lines → open a picker
        """
        self.ensure_one()
        tlines = self.order_line.filtered("is_transport")
        if not tlines:
            return False
        if len(tlines) == 1:
            return tlines[0].action_configure_transport()

        preferred = tlines.filtered(lambda l: not l.transport_config_id)[:1] or tlines[0]
        selector = self.env["cpq.transport.line.selector"].create({
            "order_id": self.id,
            "line_id": preferred.id,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Choose a transport line to configure"),
            "res_model": "cpq.transport.line.selector",
            "res_id": selector.id,
            "view_mode": "form",
            "target": "new",
            "context": {"cpq_transport_selector": True},
        }


class CpqTransportLineSelector(models.TransientModel):
    """Wizard used when several transport lines exist on the same order."""
    _name = "cpq.transport.line.selector"
    _description = "CPQ Transport Line Selection"

    order_id = fields.Many2one(
        "sale.order", required=True, ondelete="cascade",
    )
    line_id = fields.Many2one(
        "sale.order.line",
        string="Transport line",
        domain="[('order_id', '=', order_id), ('is_transport', '=', True)]",
        required=True,
    )
    line_summary = fields.Char(
        related="line_id.transport_summary",
        string="Current configuration",
        readonly=True,
    )

    def action_open_configurator(self):
        self.ensure_one()
        return self.line_id.action_configure_transport()
