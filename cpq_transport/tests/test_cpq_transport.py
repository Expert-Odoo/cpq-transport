# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

DELTA = 0.01


@tagged("post_install", "-at_install", "cpq_transport")
class TestCpqTransport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})

        # Regular product
        cls.other_product = cls.env["product.product"].create({
            "name": "Regular Product",
            "type": "consu",
            "list_price": 10.0,
        })

        # Transport product : Odoo product + linked cpq.transport.product
        cls.transport_product = cls.env["product.product"].create({
            "name": "Test Transport",
            "type": "service",
            "list_price": 0.0,
        })
        cls.cpq_transport = cls.env["cpq.transport.product"].create({
            "name": "Local delivery",
            "product_tmpl_id": cls.transport_product.product_tmpl_id.id,
        })

    def _make_order(self, product=None):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": (product or self.transport_product).id,
        })
        return order, line

    # ------------------------------------------------------------------
    def test_01_is_transport_flag_propagates(self):
        _, line = self._make_order()
        self.assertTrue(line.is_transport)
        self.assertEqual(line.cpq_transport_product_id, self.cpq_transport)
        _, line2 = self._make_order(product=self.other_product)
        self.assertFalse(line2.is_transport)
        self.assertFalse(line2.cpq_transport_product_id)

    def test_02_compute_price_one_way(self):
        _, line = self._make_order()
        cfg = self.env["cpq.transport.config"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "one_way", "price_per_km": 2.0, "one_way_km": 100.0,
        })
        self.assertAlmostEqual(cfg.computed_price, 200.0, delta=DELTA)

    def test_03_compute_price_round_trip(self):
        _, line = self._make_order()
        cfg = self.env["cpq.transport.config"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "round_trip", "price_per_km": 2.0, "one_way_km": 100.0,
        })
        self.assertAlmostEqual(cfg.computed_price, 400.0, delta=DELTA)

    def test_04_summary_format(self):
        _, line = self._make_order()
        cfg = self.env["cpq.transport.config"].create({
            "sale_line_id": line.id,
            "origin_address": "Paris", "destination_address": "Lyon",
            "trip_type": "round_trip", "price_per_km": 2.0, "one_way_km": 465.0,
        })
        self.assertIn("Paris", cfg.summary)
        self.assertIn("Lyon", cfg.summary)
        self.assertIn("930.00 km", cfg.summary)

    def test_05_is_stale_after_address_change(self):
        _, line = self._make_order()
        cfg = self.env["cpq.transport.config"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "one_way", "price_per_km": 1.0, "one_way_km": 50.0,
            "last_signature": "a|b",
        })
        self.assertFalse(cfg.is_stale)
        cfg.origin_address = "C"
        self.assertTrue(cfg.is_stale)

    def test_06_wizard_validate_updates_line_price(self):
        _, line = self._make_order()
        wiz = self.env["cpq.transport.wizard"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "one_way", "price_per_km": 2.0,
            "one_way_km": 100.0, "state": "computed",
            "last_signature": "a|b",
        })
        wiz.action_validate()
        self.assertTrue(line.transport_config_id)
        self.assertAlmostEqual(line.price_unit, 200.0, delta=DELTA)
        self.assertAlmostEqual(line.product_uom_qty, 1.0, delta=DELTA)

    def test_07_default_price_per_km_from_product(self):
        """Product-level default_price_per_km is used when configuring transport."""
        self.cpq_transport.default_price_per_km = 3.0
        _, line = self._make_order()
        action = line.action_configure_transport()
        wiz = self.env["cpq.transport.wizard"].browse(action["res_id"])
        self.assertAlmostEqual(wiz.price_per_km, 3.0, delta=DELTA)

    def test_08_zero_results_raises_usererror(self):
        _, line = self._make_order()
        self.env["ir.config_parameter"].sudo().set_param(
            "cpq_transport.gmaps_api_key", "FAKE"
        )
        wiz = self.env["cpq.transport.wizard"].create({
            "sale_line_id": line.id,
            "origin_address": "X", "destination_address": "Y",
            "trip_type": "one_way", "price_per_km": 1.0,
        })
        with patch(
            "odoo.addons.cpq_transport.models.gmaps_service.GoogleMapsService.get_distance_km",
            return_value=(None, "ZERO_RESULTS", "No route"),
        ):
            with self.assertRaises(UserError):
                wiz.action_compute_distance()

    def test_09_missing_api_key_raises_usererror(self):
        _, line = self._make_order()
        self.env["ir.config_parameter"].sudo().set_param(
            "cpq_transport.gmaps_api_key", ""
        )
        wiz = self.env["cpq.transport.wizard"].create({
            "sale_line_id": line.id,
            "origin_address": "X", "destination_address": "Y",
            "trip_type": "one_way", "price_per_km": 1.0,
        })
        with self.assertRaises(UserError):
            wiz.action_compute_distance()

    def test_10_currency_follows_order(self):
        usd = self.env.ref("base.USD")
        pricelist = self.env["product.pricelist"].create({
            "name": "Test USD", "currency_id": usd.id,
        })
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "pricelist_id": pricelist.id,
        })
        line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.transport_product.id,
        })
        cfg = self.env["cpq.transport.config"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "one_way", "price_per_km": 1.0, "one_way_km": 10.0,
        })
        self.assertEqual(cfg.currency_id.name, "USD")

    def test_11_config_deleted_when_line_deleted(self):
        _, line = self._make_order()
        cfg = self.env["cpq.transport.config"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "one_way", "price_per_km": 1.0, "one_way_km": 10.0,
        })
        cfg_id = cfg.id
        line.unlink()
        self.assertFalse(self.env["cpq.transport.config"].browse(cfg_id).exists())

    def test_12_stale_blocks_validate(self):
        _, line = self._make_order()
        wiz = self.env["cpq.transport.wizard"].create({
            "sale_line_id": line.id,
            "origin_address": "A", "destination_address": "B",
            "trip_type": "one_way", "price_per_km": 1.0,
            "one_way_km": 10.0, "state": "computed",
            "last_signature": "a|b",
        })
        wiz.origin_address = "Z"
        wiz._onchange_addresses()
        with self.assertRaises(UserError):
            wiz.action_validate()

    def test_13_routes_service_ok_mock(self):
        from odoo.addons.cpq_transport.models.gmaps_service import GoogleMapsService
        import json as _json
        from unittest.mock import MagicMock, patch as _p

        payload = [{
            "originIndex": 0, "destinationIndex": 0,
            "status": {}, "condition": "ROUTE_EXISTS",
            "distanceMeters": 465000, "duration": "18000s",
        }]
        mock_resp = MagicMock()
        mock_resp.read.return_value = _json.dumps(payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with _p("urllib.request.urlopen", return_value=mock_resp):
            km, status, err = GoogleMapsService.get_distance_km("Paris", "Lyon", "FAKE")
        self.assertEqual(status, "OK")
        self.assertIsNone(err)
        self.assertAlmostEqual(km, 465.0, delta=DELTA)

    def test_13b_routes_service_route_not_found(self):
        from odoo.addons.cpq_transport.models.gmaps_service import GoogleMapsService
        import json as _json
        from unittest.mock import MagicMock, patch as _p

        payload = [{
            "originIndex": 0, "destinationIndex": 0,
            "status": {}, "condition": "ROUTE_NOT_FOUND",
        }]
        mock_resp = MagicMock()
        mock_resp.read.return_value = _json.dumps(payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        with _p("urllib.request.urlopen", return_value=mock_resp):
            km, status, err = GoogleMapsService.get_distance_km("A", "B", "FAKE")
        self.assertEqual(status, "ZERO_RESULTS")
        self.assertIsNone(km)

    def test_14_gmaps_missing_key(self):
        from odoo.addons.cpq_transport.models.gmaps_service import GoogleMapsService
        km, status, err = GoogleMapsService.get_distance_km("A", "B", "")
        self.assertEqual(status, "MISSING_KEY")
        self.assertIsNone(km)

    def test_15_smart_button_line_count(self):
        """Multi-transport-lines : smart button reflects the number of lines."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        for _ in range(3):
            self.env["sale.order.line"].create({
                "order_id": order.id, "product_id": self.transport_product.id,
            })
        # Add a non-transport line — should not be counted
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.other_product.id,
        })
        order.invalidate_recordset()
        self.assertEqual(order.transport_line_count, 3)
        self.assertEqual(order.transport_unconfigured_count, 3)

    def test_16_unique_product_tmpl_constraint(self):
        """A product.template can only be linked to ONE cpq.transport.product."""
        from psycopg2 import IntegrityError
        from odoo.tools.misc import mute_logger
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.env["cpq.transport.product"].create({
                    "name": "Duplicate",
                    "product_tmpl_id": self.transport_product.product_tmpl_id.id,
                })
                self.env.flush_all()

    def test_17_multi_lines_selector_opens(self):
        """With >1 transport line, action returns the selector wizard."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        for _ in range(2):
            self.env["sale.order.line"].create({
                "order_id": order.id, "product_id": self.transport_product.id,
            })
        order.invalidate_recordset()
        action = order.action_configure_transport_lines()
        self.assertEqual(action["res_model"], "cpq.transport.line.selector")

    def test_18_single_line_opens_wizard_directly(self):
        """With exactly 1 transport line, action opens the config wizard."""
        _, _line = self._make_order()
        order = _line.order_id
        action = order.action_configure_transport_lines()
        self.assertEqual(action["res_model"], "cpq.transport.wizard")
